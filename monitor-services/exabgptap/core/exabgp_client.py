import multiprocessing as mp
import os
import signal
import threading
import time

import pytricia
import redis
import requests
import ujson as json
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import key_generator
from artemis_utils import mformat_validator
from artemis_utils import normalize_msg_path
from artemis_utils import ping_redis
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import REDIS_PORT
from artemis_utils.rabbitmq_util import create_exchange
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
}

# global vars
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60
AUTOCONF_INTERVAL = 60
SERVICE_NAME = "exabgptap"
CONFIGURATION_HOST = "configuration"
PREFIXTREE_HOST = "prefixtree"
REST_PORT = int(os.getenv("REST_PORT", 3000))

# TODO: introduce redis-based restart logic (if no data is received within certain time frame)


def start_data_worker(shared_memory_manager_dict):
    shared_memory_locks["data_worker"].acquire()
    if not shared_memory_manager_dict["data_worker_configured"]:
        shared_memory_locks["data_worker"].release()
        return "not configured, will not start"
    if shared_memory_manager_dict["data_worker_running"]:
        log.info("data worker already running")
        shared_memory_locks["data_worker"].release()
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
        if data_worker.autoconf_timer_thread is not None:
            data_worker.autoconf_timer_thread.join()
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
        shared_memory_locks["data_worker"].acquire()
        if not shared_memory_manager_dict["data_worker_running"]:
            shared_memory_locks["data_worker"].release()
            break
        shared_memory_locks["data_worker"].release()
        time.sleep(1)
    message = "instructed to stop"
    return message


def configure_exabgp(msg, shared_memory_manager_dict):
    config = msg
    try:
        # check newer config
        shared_memory_locks["config_timestamp"].acquire()
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        shared_memory_locks["config_timestamp"].release()
        if config["timestamp"] > config_timestamp:
            # get monitors
            r = requests.get("http://{}:{}/monitors".format(PREFIXTREE_HOST, REST_PORT))
            monitors = r.json()["monitors"]

            # check if "exabgp" is configured at all
            if "exabgp" not in monitors:
                stop_msg = stop_data_worker(shared_memory_manager_dict)
                log.info(stop_msg)
                shared_memory_locks["data_worker"].acquire()
                shared_memory_manager_dict["data_worker_configured"] = False
                shared_memory_locks["data_worker"].release()
                return {"success": True, "message": "data worker not in configuration"}

            # check if the worker should run (if configured)
            shared_memory_locks["data_worker"].acquire()
            should_run = shared_memory_manager_dict["data_worker_should_run"]
            shared_memory_locks["data_worker"].release()

            # make sure that data worker is stopped
            stop_msg = stop_data_worker(shared_memory_manager_dict)
            log.info(stop_msg)

            # get monitored prefixes
            r = requests.get(
                "http://{}:{}/monitoredPrefixes".format(PREFIXTREE_HOST, REST_PORT)
            )
            shared_memory_locks["monitored_prefixes"].acquire()
            shared_memory_manager_dict["monitored_prefixes"] = set(
                r.json()["monitored_prefixes"]
            )
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
            shared_memory_locks["hosts"].acquire()
            shared_memory_manager_dict["hosts"] = hosts
            shared_memory_locks["hosts"].release()

            # signal that data worker is configured
            shared_memory_locks["data_worker"].acquire()
            shared_memory_manager_dict["data_worker_configured"] = True
            shared_memory_locks["data_worker"].release()

            shared_memory_locks["config_timestamp"].acquire()
            shared_memory_manager_dict["config_timestamp"] = config_timestamp
            shared_memory_locks["config_timestamp"].release()

            # start the data worker only if it should be running
            if should_run:
                start_msg = start_data_worker(shared_memory_manager_dict)
                log.info(start_msg)

        return {"success": True, "message": "configured"}
    except Exception:
        log.exception("exception")
        return {"success": False, "message": "error during data worker configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

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
                {"success": False, "message": "error during data worker configuration"}
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
        :return: {"status" : <unconfigured|running|stopped>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
        elif not self.shared_memory_manager_dict["data_worker_configured"]:
            status = "unconfigured"
        shared_memory_locks["data_worker"].release()
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
        self.shared_memory_manager_dict["data_worker_should_run"] = False
        self.shared_memory_manager_dict["data_worker_configured"] = False
        self.shared_memory_manager_dict["monitored_prefixes"] = set()
        self.shared_memory_manager_dict["hosts"] = {}
        self.shared_memory_manager_dict["autoconf_updates"] = {}
        self.shared_memory_manager_dict["config_timestamp"] = -1

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


class ExaBGPDataWorker:
    """
    RabbitMQ Producer for the ExaBGP tap Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        shared_memory_locks["monitored_prefixes"].acquire()
        self.prefixes = self.shared_memory_manager_dict["monitored_prefixes"]
        shared_memory_locks["monitored_prefixes"].release()
        shared_memory_locks["hosts"].acquire()
        self.hosts = self.shared_memory_manager_dict["hosts"]
        shared_memory_locks["hosts"].release()
        self.autoconf_timer_thread = None
        self.previous_redis_autoconf_updates_counter = 0

        # EXCHANGES
        self.update_exchange = create_exchange(
            "bgp-update", self.connection, declare=True
        )
        self.autoconf_exchange = create_exchange("autoconf", connection, declare=True)

    def setup_autoconf_update_timer(self):
        """
        Timer for autoconf update message send. Periodically (every AUTOCONF_INTERVAL seconds),
        it sends buffered autoconf messages to configuration for processing
        :return:
        """
        shared_memory_locks["data_worker"].acquire()
        if not self.shared_memory_manager_dict["data_worker_should_run"]:
            shared_memory_locks["data_worker"].release()
            return
        shared_memory_locks["data_worker"].release()
        self.autoconf_timer_thread = threading.Timer(
            interval=AUTOCONF_INTERVAL, function=self.send_autoconf_updates
        )
        self.autoconf_timer_thread.start()

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
            keys_to_remove = (
                set(self.shared_memory_manager_dict["autoconf_updates"].keys())
                - autoconf_update_keys_to_process
            )
            for key in keys_to_remove:
                del self.shared_memory_manager_dict["autoconf_updates"][key]
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["autoconf_updates"].release()

        if len(autoconf_update_keys_to_process) == 0:
            self.previous_redis_autoconf_updates_counter = 0
            self.setup_autoconf_update_timer()
            return

        # check if configuration is overwhelmed; if yes, back off to reduce aggressiveness
        if self.previous_redis_autoconf_updates_counter == len(
            autoconf_update_keys_to_process
        ):
            self.setup_autoconf_update_timer()
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
            self.previous_redis_autoconf_updates_counter = len(
                autoconf_update_keys_to_process
            )
            self.setup_autoconf_update_timer()

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
                prefixes = list(self.prefixes)
            prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
            for prefix in prefixes:
                ip_version = get_ip_version(prefix)
                prefix_tree[ip_version].insert(prefix, "")

            # set up message validator
            validator = mformat_validator()

            def handle_exabgp_msg(bgp_message):
                redis.set(
                    "exabgp_seen_bgp_update",
                    "1",
                    ex=int(
                        os.getenv(
                            "MON_TIMEOUT_LAST_BGP_UPDATE",
                            DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                        )
                    ),
                )
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
                                        autoconf_updates = self.shared_memory_manager_dict[
                                            "autoconf_updates"
                                        ]
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
                            log.warning("Invalid format message: {}".format(msg))
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
        redis.set(
            "exabgp_seen_bgp_update",
            "1",
            ex=int(
                os.getenv(
                    "MON_TIMEOUT_LAST_BGP_UPDATE", DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE
                )
            ),
        )

        # start autoconf timer thread
        if self.autoconf_timer_thread is not None:
            self.autoconf_timer_thread.cancel()
        self.setup_autoconf_update_timer()

        # start host processes
        host_processes = []
        for host in self.hosts:
            host_process = mp.Process(target=self.run_host_sio_process, args=(host,))
            host_processes.append(host_process)
            host_process.start()

        while True:
            shared_memory_locks["data_worker"].acquire()
            if not self.shared_memory_manager_dict["data_worker_should_run"]:
                shared_memory_locks["data_worker"].release()
                for host_process in host_processes:
                    host_process.terminate()
                break
            shared_memory_locks["data_worker"].release()
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

    # start REST within main process
    exabgpTapService.start_rest_app()


if __name__ == "__main__":
    main()
