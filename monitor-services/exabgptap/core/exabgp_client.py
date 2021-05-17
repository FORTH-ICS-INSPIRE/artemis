import multiprocessing as mp
import signal
import time

import pytricia
import redis
import requests
import ujson as json
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.constants import DATABASE_HOST
from artemis_utils.constants import PREFIXTREE_HOST
from artemis_utils.envvars import MON_TIMEOUT_LAST_BGP_UPDATE
from artemis_utils.envvars import RABBITMQ_URI
from artemis_utils.envvars import REDIS_HOST
from artemis_utils.envvars import REDIS_PORT
from artemis_utils.envvars import REST_PORT
from artemis_utils.rabbitmq import create_exchange
from artemis_utils.redis import ping_redis
from artemis_utils.redis import RedisExpiryChecker
from artemis_utils.updates import key_generator
from artemis_utils.updates import MformatValidator
from artemis_utils.updates import normalize_msg_path
from kombu import Connection
from kombu import Producer
from socketIO_client import BaseNamespace
from socketIO_client import SocketIO
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler


# logger
log = get_logger()

# shared memory object locks
shared_memory_locks = {
    "data_worker": mp.Lock(),
    "monitored_prefixes": mp.Lock(),
    "hosts": mp.Lock(),
    "autoconf_updates": mp.Lock(),
    "config_timestamp": mp.Lock(),
    "service_reconfiguring": mp.Lock(),
}

# global vars
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
AUTOCONF_INTERVAL = 10
SERVICE_NAME = "exabgptap"


def start_data_worker(shared_memory_manager_dict):
    shared_memory_locks["data_worker"].acquire()
    if not shared_memory_manager_dict["data_worker_configured"]:
        shared_memory_locks["data_worker"].release()
        return "not configured, will not start"
    if shared_memory_manager_dict["data_worker_running"]:
        shared_memory_locks["data_worker"].release()
        log.info("data worker already running")
        return "already running"
    shared_memory_locks["data_worker"].release()
    mp.Process(
        target=run_data_worker_process, args=(shared_memory_manager_dict,)
    ).start()
    return "instructed to start"


def run_data_worker_process(shared_memory_manager_dict):
    try:
        with Connection(RABBITMQ_URI) as connection:
            shared_memory_locks["data_worker"].acquire()
            data_worker = ExaBGPDataWorker(connection, shared_memory_manager_dict)
            shared_memory_manager_dict["data_worker_should_run"] = True
            shared_memory_manager_dict["data_worker_running"] = True
            shared_memory_locks["data_worker"].release()
            log.info("data worker started")
            data_worker.run()
    except Exception:
        log.exception("exception")
    finally:
        shared_memory_locks["data_worker"].acquire()
        shared_memory_manager_dict["data_worker_running"] = False
        shared_memory_locks["data_worker"].release()
        log.info("data worker stopped")


def stop_data_worker(shared_memory_manager_dict):
    shared_memory_locks["data_worker"].acquire()
    shared_memory_manager_dict["data_worker_should_run"] = False
    shared_memory_locks["data_worker"].release()
    # make sure that data worker is stopped
    while True:
        if not shared_memory_manager_dict["data_worker_running"]:
            break
        time.sleep(1)
    message = "instructed to stop"
    return message


def configure_exabgp(msg, shared_memory_manager_dict):
    config = msg
    try:
        # check newer config
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        if config["timestamp"] > config_timestamp:
            shared_memory_locks["service_reconfiguring"].acquire()
            shared_memory_manager_dict["service_reconfiguring"] = True
            shared_memory_locks["service_reconfiguring"].release()

            # get monitors
            r = requests.get("http://{}:{}/monitors".format(DATABASE_HOST, REST_PORT))
            monitors = r.json()["monitors"]

            # check if "exabgp" is configured at all
            if "exabgp" not in monitors:
                if shared_memory_manager_dict["data_worker_running"]:
                    stop_msg = stop_data_worker(shared_memory_manager_dict)
                    log.info(stop_msg)
                shared_memory_locks["data_worker"].acquire()
                shared_memory_manager_dict["data_worker_configured"] = False
                shared_memory_locks["data_worker"].release()
                shared_memory_locks["service_reconfiguring"].acquire()
                shared_memory_manager_dict["service_reconfiguring"] = False
                shared_memory_locks["service_reconfiguring"].release()
                return {"success": True, "message": "data worker not in configuration"}

            # check if the worker should run (if configured)
            should_run = shared_memory_manager_dict["data_worker_should_run"]

            # make sure that data worker is stopped
            stop_msg = stop_data_worker(shared_memory_manager_dict)
            log.info(stop_msg)

            # get monitored prefixes
            r = requests.get(
                "http://{}:{}/monitoredPrefixes".format(PREFIXTREE_HOST, REST_PORT)
            )
            shared_memory_locks["monitored_prefixes"].acquire()
            shared_memory_manager_dict["monitored_prefixes"] = r.json()[
                "monitored_prefixes"
            ]
            shared_memory_locks["monitored_prefixes"].release()

            # get host configuration
            hosts = {}
            for exabgp_monitor in monitors["exabgp"]:
                host = "{}:{}".format(exabgp_monitor["ip"], exabgp_monitor["port"])
                hosts[host] = set()
                if "autoconf" in exabgp_monitor:
                    hosts[host].add("autoconf")
                if "learn_neighbors" in exabgp_monitor:
                    hosts[host].add("learn_neighbors")
                hosts[host] = list(hosts[host])
            shared_memory_locks["hosts"].acquire()
            shared_memory_manager_dict["hosts"] = hosts
            shared_memory_locks["hosts"].release()

            # signal that data worker is configured
            shared_memory_locks["data_worker"].acquire()
            shared_memory_manager_dict["data_worker_configured"] = True
            shared_memory_locks["data_worker"].release()

            shared_memory_locks["config_timestamp"].acquire()
            shared_memory_manager_dict["config_timestamp"] = config["timestamp"]
            shared_memory_locks["config_timestamp"].release()

            # start the data worker only if it should be running
            if should_run:
                start_msg = start_data_worker(shared_memory_manager_dict)
                log.info(start_msg)

        shared_memory_locks["service_reconfiguring"].acquire()
        shared_memory_manager_dict["service_reconfiguring"] = False
        shared_memory_locks["service_reconfiguring"].release()
        return {"success": True, "message": "configured"}
    except Exception:
        log.exception("exception")
        shared_memory_locks["service_reconfiguring"].acquire()
        shared_memory_manager_dict["service_reconfiguring"] = False
        shared_memory_locks["service_reconfiguring"].release()
        return {"success": False, "message": "error during service configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Provides current configuration primitives (in the form of a JSON dict) to the requester.
        Format:
        {
            "data_worker_should_run": <bool>,
            "data_worker_configured": <bool>,
            "monitored_prefixes": <list>,
            "hosts": <dict>,
            "config_timestamp": <timestamp>
        }
        """
        ret_dict = {}

        ret_dict["data_worker_should_run"] = self.shared_memory_manager_dict[
            "data_worker_should_run"
        ]
        ret_dict["data_worker_configured"] = self.shared_memory_manager_dict[
            "data_worker_configured"
        ]

        ret_dict["monitored_prefixes"] = self.shared_memory_manager_dict[
            "monitored_prefixes"
        ]

        ret_dict["hosts"] = self.shared_memory_manager_dict["hosts"]

        ret_dict["config_timestamp"] = self.shared_memory_manager_dict[
            "config_timestamp"
        ]

        self.write(ret_dict)

    def post(self):
        """
        Handler for posted configuration from configuration.
        Note that for performance reasons the eventual needed elements
        are collected from the prefix tree service.
        :return: {"success": True|False, "message": <message>}
        """
        try:
            msg = json.loads(self.request.body)
            self.write(configure_exabgp(msg, self.shared_memory_manager_dict))
        except Exception:
            self.write(
                {"success": False, "message": "error during service configuration"}
            )


class HealthHandler(RequestHandler):
    """
    REST request handler for health checks.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Extract the status of a service via a GET request.
        :return: {"status" : <unconfigured|running|stopped><,reconfiguring>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
        elif not self.shared_memory_manager_dict["data_worker_configured"]:
            status = "unconfigured"
        shared_memory_locks["data_worker"].release()
        if self.shared_memory_manager_dict["service_reconfiguring"]:
            status += ",reconfiguring"
        self.write({"status": status})


class ControlHandler(RequestHandler):
    """
    REST request handler for control commands.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def post(self):
        """
        Instruct a service to start or stop by posting a command.
        Sample request body
        {
            "command": <start|stop>
        }
        :return: {"success": True|False, "message": <message>}
        """
        try:
            msg = json.loads(self.request.body)
            command = msg["command"]
            # start/stop data_worker
            if command == "start":
                message = start_data_worker(self.shared_memory_manager_dict)
                self.write({"success": True, "message": message})
            elif command == "stop":
                message = stop_data_worker(self.shared_memory_manager_dict)
                self.write({"success": True, "message": message})
            else:
                self.write({"success": False, "message": "unknown command"})
        except Exception:
            log.exception("Exception")
            self.write({"success": False, "message": "error during control"})


class ExaBGPTap:
    """
    ExaBGP Tap REST Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["service_reconfiguring"] = False
        self.shared_memory_manager_dict["data_worker_should_run"] = False
        self.shared_memory_manager_dict["data_worker_configured"] = False
        self.shared_memory_manager_dict["monitored_prefixes"] = list()
        self.shared_memory_manager_dict["hosts"] = {}
        self.shared_memory_manager_dict["autoconf_updates"] = {}
        self.shared_memory_manager_dict["config_timestamp"] = -1
        self.shared_memory_manager_dict["autoconf_running"] = False

        log.info("service initiated")

    def make_rest_app(self):
        return Application(
            [
                (
                    "/config",
                    ConfigHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
                (
                    "/control",
                    ControlHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
                (
                    "/health",
                    HealthHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
            ]
        )

    def start_rest_app(self):
        app = self.make_rest_app()
        app.listen(REST_PORT)
        log.info("REST worker started and listening to port {}".format(REST_PORT))
        IOLoop.current().start()


class AutoconfUpdater:
    """
    Autoconf Updater.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.previous_redis_autoconf_updates = set()

        # EXCHANGES
        self.autoconf_exchange = create_exchange("autoconf", connection, declare=True)

    def send_autoconf_updates(self):
        # clean up unneeded updates stored in RAM (with thread-safe access)
        shared_memory_locks["autoconf_updates"].acquire()
        autoconf_update_keys_to_process = set(
            map(
                lambda x: x.decode("ascii"),
                redis.smembers("autoconf-update-keys-to-process"),
            )
        )
        try:
            autoconf_updates = self.shared_memory_manager_dict["autoconf_updates"]
            keys_to_remove = (
                set(autoconf_updates.keys()) - autoconf_update_keys_to_process
            )
            for key in keys_to_remove:
                del autoconf_updates[key]
            self.shared_memory_manager_dict["autoconf_updates"] = autoconf_updates
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["autoconf_updates"].release()

        if len(autoconf_update_keys_to_process) == 0:
            return

        # check if configuration is overwhelmed; if yes, back off to reduce aggressiveness
        if self.previous_redis_autoconf_updates == autoconf_update_keys_to_process:
            log.warning("autoconf mechanism is overwhelmed, will re-try next round")
            return

        try:
            autoconf_updates_keys_to_send = list(autoconf_update_keys_to_process)
            autoconf_updates_to_send = []
            for update_key in autoconf_updates_keys_to_send:
                shared_memory_locks["autoconf_updates"].acquire()
                autoconf_updates_to_send.append(
                    self.shared_memory_manager_dict["autoconf_updates"][update_key]
                )
                shared_memory_locks["autoconf_updates"].release()
            log.info(
                "Sending {} autoconf updates to be filtered via prefixtree".format(
                    len(autoconf_updates_to_send)
                )
            )

            with Producer(self.connection) as producer:
                producer.publish(
                    autoconf_updates_to_send,
                    exchange=self.autoconf_exchange,
                    routing_key="update",
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
        except Exception:
            log.exception("exception")
        finally:
            self.previous_redis_autoconf_updates = set(autoconf_update_keys_to_process)

    def run(self):
        while True:
            # no need to ever stop autoconf mechanism from the moment it starts
            # independent of what happens to the parent (e.g., if conf changes,
            # etc.)
            self.send_autoconf_updates()
            time.sleep(AUTOCONF_INTERVAL)


class ExaBGPDataWorker:
    """
    RabbitMQ Producer for the ExaBGP tap Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.prefixes = self.shared_memory_manager_dict["monitored_prefixes"]
        self.hosts = self.shared_memory_manager_dict["hosts"]
        self.autoconf_updater = None

        # EXCHANGES
        self.update_exchange = create_exchange(
            "bgp-update", self.connection, declare=True
        )
        self.autoconf_exchange = create_exchange("autoconf", connection, declare=True)

        log.info("data worker initiated")

    def run_host_sio_process(self, host):
        def exit_gracefully(signum, frame):
            if sio is not None:
                sio.disconnect()
                log.info("'{}' sio disconnected".format(host))
            log.info("'{}' client exited".format(host))
            shared_memory_locks["data_worker"].acquire()
            self.shared_memory_manager_dict["data_worker_should_run"] = False
            shared_memory_locks["data_worker"].release()

        # register signal handler
        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)

        try:
            # set autoconf booleans
            autoconf = False
            learn_neighbors = False
            if "autoconf" in self.hosts[host]:
                autoconf = True
                if "learn_neighbors" in self.hosts[host]:
                    learn_neighbors = True

            # build monitored prefix tree
            if autoconf:
                prefixes = ["0.0.0.0/0", "::/0"]
            else:
                prefixes = self.prefixes
            prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
            for prefix in prefixes:
                ip_version = get_ip_version(prefix)
                prefix_tree[ip_version].insert(prefix, "")

            # set up message validator
            validator = MformatValidator()

            def handle_exabgp_msg(bgp_message):
                redis.set("exabgp_seen_bgp_update", "1", ex=MON_TIMEOUT_LAST_BGP_UPDATE)
                msg = {
                    "type": bgp_message["type"],
                    "communities": bgp_message.get("communities", []),
                    "timestamp": float(bgp_message["timestamp"]),
                    "path": bgp_message.get("path", []),
                    "service": "exabgp|{}".format(host),
                    "prefix": bgp_message["prefix"],
                    "peer_asn": int(bgp_message["peer_asn"]),
                }

                this_prefix = msg["prefix"]
                ip_version = get_ip_version(this_prefix)
                if this_prefix in prefix_tree[ip_version]:
                    try:
                        if validator.validate(msg):
                            msgs = normalize_msg_path(msg)
                            for msg in msgs:
                                key_generator(msg)
                                log.debug(msg)
                                if autoconf:
                                    try:
                                        if learn_neighbors:
                                            msg["learn_neighbors"] = True
                                        shared_memory_locks[
                                            "autoconf_updates"
                                        ].acquire()
                                        autoconf_updates = (
                                            self.shared_memory_manager_dict[
                                                "autoconf_updates"
                                            ]
                                        )
                                        autoconf_updates[msg["key"]] = msg
                                        self.shared_memory_manager_dict[
                                            "autoconf_updates"
                                        ] = autoconf_updates
                                        # mark the autoconf BGP updates for configuration
                                        # processing in redis
                                        redis_pipeline = redis.pipeline()
                                        redis_pipeline.sadd(
                                            "autoconf-update-keys-to-process",
                                            msg["key"],
                                        )
                                        redis_pipeline.execute()
                                    except Exception:
                                        log.exception("exception")
                                    finally:
                                        shared_memory_locks[
                                            "autoconf_updates"
                                        ].release()
                                else:
                                    with Producer(self.connection) as producer:
                                        producer.publish(
                                            msg,
                                            exchange=self.update_exchange,
                                            routing_key="update",
                                            serializer="ujson",
                                        )
                        else:
                            log.debug("Invalid format message: {}".format(msg))
                    except BaseException:
                        log.exception(
                            "Error when normalizing BGP message: {}".format(msg)
                        )

            # set up socket-io client
            sio = SocketIO("http://" + host, namespace=BaseNamespace)
            log.info("'{}' client ready to receive sio messages".format(host))
            sio.on("exa_message", handle_exabgp_msg)
            sio.emit("exa_subscribe", {"prefixes": prefixes})
            if autoconf:
                route_refresh_command_v4 = "announce route-refresh ipv4 unicast"
                sio.emit("route_command", {"command": route_refresh_command_v4})
                route_refresh_command_v6 = "announce route-refresh ipv6 unicast"
                sio.emit("route_command", {"command": route_refresh_command_v6})
            sio.wait()
        except Exception:
            log.exception("exception")

    def run(self):
        # update redis
        ping_redis(redis)
        redis.set("exabgp_seen_bgp_update", "1", ex=MON_TIMEOUT_LAST_BGP_UPDATE)

        autoconf_running = self.shared_memory_manager_dict["autoconf_running"]
        if not autoconf_running:
            log.info("setting up autoconf updater process...")
            with Connection(RABBITMQ_URI) as connection:
                self.autoconf_updater = AutoconfUpdater(
                    connection, self.shared_memory_manager_dict
                )
                shared_memory_locks["autoconf_updates"].acquire()
                self.shared_memory_manager_dict["autoconf_running"] = True
                shared_memory_locks["autoconf_updates"].release()
                mp.Process(target=self.autoconf_updater.run).start()
            log.info("autoignore checker set up")

        # start host processes
        host_processes = []
        for host in self.hosts:
            host_process = mp.Process(target=self.run_host_sio_process, args=(host,))
            host_processes.append(host_process)
            host_process.start()

        while True:
            if not self.shared_memory_manager_dict["data_worker_should_run"]:
                for host_process in host_processes:
                    host_process.terminate()
                break
            time.sleep(1)


def main():
    # initiate ExaBGP tap service with REST
    exabgpTapService = ExaBGPTap()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_exabgp(
            r.json(), exabgpTapService.shared_memory_manager_dict
        )
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # initiate redis checker
    log.info("setting up redis expiry checker process...")
    redis_checker = RedisExpiryChecker(
        redis=redis,
        shared_memory_manager_dict=exabgpTapService.shared_memory_manager_dict,
        monitor="exabgp",
        stop_data_worker_fun=stop_data_worker,
    )
    mp.Process(target=redis_checker.run).start()
    log.info("redis expiry checker set up")

    # start REST within main process
    exabgpTapService.start_rest_app()


if __name__ == "__main__":
    main()
