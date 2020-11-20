import multiprocessing as mp
import os
import time

import redis
import requests
import ujson as json
from artemis_utils import get_logger
from artemis_utils import ping_redis
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import REDIS_PORT
from artemis_utils.rabbitmq_util import create_exchange
from kombu import Connection
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

# import threading
# from artemis_utils import key_generator
# from artemis_utils import load_json
# from artemis_utils import mformat_validator
# from artemis_utils import normalize_msg_path
# from kombu import Producer
# from netaddr import IPAddress
# from netaddr import IPNetwork
# from socketIO_client import BaseNamespace
# from socketIO_client import SocketIO

# logger
log = get_logger()

# shared memory object locks
shared_memory_locks = {
    "data_worker": mp.Lock(),
    "monitored_prefixes": mp.Lock(),
    "hosts": mp.Lock(),
}

# global vars
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60
AUTOCONF_INTERVAL = 10
MAX_AUTOCONF_UPDATES = 100
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


def configure_exabgp(shared_memory_manager_dict):
    try:
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
            self.write(configure_exabgp(self.shared_memory_manager_dict))
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

        # EXCHANGES
        self.update_exchange = create_exchange(
            "bgp-update", self.connection, declare=True
        )

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

        # TODO: properly set up socket io and other tasks (see comments)
        while True:
            shared_memory_locks["data_worker"].acquire()
            if not self.shared_memory_manager_dict["data_worker_should_run"]:
                shared_memory_locks["data_worker"].release()
                break
            shared_memory_locks["data_worker"].release()
            log.info(self.shared_memory_manager_dict)
            time.sleep(10)


# class ExaBGP:
#     def __init__(self, prefixes_file, host, autoconf=False, learn_neighbors=False):
#         self.module_name = "exabgp|{}".format(host)
#         self.host = host
#         self.should_stop = False
#         # use /0 if autoconf
#         if autoconf:
#             self.prefixes = ["0.0.0.0/0", "::/0"]
#         else:
#             self.prefixes = load_json(prefixes_file)
#         assert self.prefixes is not None
#         self.sio = None
#         self.connection = None
#         self.update_exchange = None
#         self.config_exchange = None
#         self.config_queue = None
#         self.autoconf = autoconf
#         self.autoconf_timer_thread = None
#         self.autoconf_updates = {}
#         self.learn_neighbors = learn_neighbors
#         self.previous_redis_autoconf_updates_counter = 0
#         signal.signal(signal.SIGTERM, self.exit)
#         signal.signal(signal.SIGINT, self.exit)
#         signal.signal(signal.SIGCHLD, signal.SIG_IGN)
#
#     def setup_autoconf_update_timer(self):
#         """
#         Timer for autoconf update message send. Periodically (every AUTOCONF_INTERVAL seconds),
#         it sends buffered autoconf messages to configuration for processing
#         :return:
#         """
#         autoconf_update_keys_to_process = set(
#             map(
#                 lambda x: x.decode("ascii"),
#                 redis.smembers("autoconf-update-keys-to-process"),
#             )
#         )
#         if self.should_stop and len(autoconf_update_keys_to_process) == 0:
#             if self.sio is not None:
#                 self.sio.disconnect()
#             if self.connection is not None:
#                 self.connection.release()
#             redis.set("exabgp_{}_running".format(self.host), 0)
#             log.info("ExaBGP exited")
#             return
#         self.autoconf_timer_thread = Timer(
#             interval=AUTOCONF_INTERVAL, function=self.send_autoconf_updates
#         )
#         self.autoconf_timer_thread.start()
#
#     def send_autoconf_updates(self):
#         # clean up unneeded updates stored in RAM (with thread-safe access)
#         lock.acquire()
#         autoconf_update_keys_to_process = set(
#             map(
#                 lambda x: x.decode("ascii"),
#                 redis.smembers("autoconf-update-keys-to-process"),
#             )
#         )
#         try:
#             keys_to_remove = (
#                 set(self.autoconf_updates.keys()) - autoconf_update_keys_to_process
#             )
#             for key in keys_to_remove:
#                 del self.autoconf_updates[key]
#         except Exception:
#             log.exception("exception")
#         finally:
#             lock.release()
#
#         if len(autoconf_update_keys_to_process) == 0:
#             self.previous_redis_autoconf_updates_counter = 0
#             self.setup_autoconf_update_timer()
#             return
#
#         # check if configuration is overwhelmed; if yes, back off to reduce aggressiveness
#         if self.previous_redis_autoconf_updates_counter == len(
#             autoconf_update_keys_to_process
#         ):
#             self.setup_autoconf_update_timer()
#             return
#
#         try:
#             autoconf_updates_keys_to_send = list(autoconf_update_keys_to_process)[
#                 :MAX_AUTOCONF_UPDATES
#             ]
#             autoconf_updates_to_send = []
#             for update_key in autoconf_updates_keys_to_send:
#                 autoconf_updates_to_send.append(self.autoconf_updates[update_key])
#             log.info(
#                 "Sending {} autoconf updates to configuration".format(
#                     len(autoconf_updates_to_send)
#                 )
#             )
#             if self.connection is None:
#                 self.connection = Connection(RABBITMQ_URI)
#             with Producer(self.connection) as producer:
#                 producer.publish(
#                     autoconf_updates_to_send,
#                     exchange=self.config_exchange,
#                     routing_key="autoconf-update",
#                     retry=True,
#                     priority=4,
#                     serializer="ujson",
#                 )
#             if self.connection is None:
#                 self.connection = Connection(RABBITMQ_URI)
#         except Exception:
#             log.exception("exception")
#         finally:
#             self.previous_redis_autoconf_updates_counter = len(
#                 autoconf_update_keys_to_process
#             )
#             self.setup_autoconf_update_timer()
#
#     def start(self):
#         with Connection(RABBITMQ_URI) as connection:
#             self.connection = connection
#             self.update_exchange = create_exchange(
#                 "bgp-update", connection, declare=True
#             )
#             self.config_exchange = create_exchange("config", connection, declare=True)
#
#             # wait until go-ahead from potentially running previous tap
#             while redis.getset("exabgp_{}_running".format(self.host), 1) == b"1":
#                 time.sleep(1)
#                 if self.should_stop:
#                     log.info("ExaBGP exited")
#                     return
#
#             if self.autoconf:
#                 if self.autoconf_timer_thread is not None:
#                     self.autoconf_timer_thread.cancel()
#                 self.setup_autoconf_update_timer()
#
#             validator = mformat_validator()
#
#             try:
#                 self.sio = SocketIO("http://" + self.host, namespace=BaseNamespace)
#
#                 def exabgp_msg(bgp_message):
#                     redis.set(
#                         "exabgp_seen_bgp_update",
#                         "1",
#                         ex=int(
#                             os.getenv(
#                                 "MON_TIMEOUT_LAST_BGP_UPDATE",
#                                 DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
#                             )
#                         ),
#                     )
#                     msg = {
#                         "type": bgp_message["type"],
#                         "communities": bgp_message.get("communities", []),
#                         "timestamp": float(bgp_message["timestamp"]),
#                         "path": bgp_message.get("path", []),
#                         "service": "exabgp|{}".format(self.host),
#                         "prefix": bgp_message["prefix"],
#                         "peer_asn": int(bgp_message["peer_asn"]),
#                     }
#                     for prefix in self.prefixes:
#                         try:
#                             base_ip, mask_length = bgp_message["prefix"].split("/")
#                             our_prefix = IPNetwork(prefix)
#                             if (
#                                 IPAddress(base_ip) in our_prefix
#                                 and int(mask_length) >= our_prefix.prefixlen
#                             ):
#                                 try:
#                                     if validator.validate(msg):
#                                         msgs = normalize_msg_path(msg)
#                                         for msg in msgs:
#                                             key_generator(msg)
#                                             log.debug(msg)
#                                             if self.autoconf:
#                                                 # thread-safe access to update dict
#                                                 lock.acquire()
#                                                 try:
#                                                     if self.learn_neighbors:
#                                                         msg["learn_neighbors"] = True
#                                                     self.autoconf_updates[
#                                                         msg["key"]
#                                                     ] = msg
#                                                     # mark the autoconf BGP updates for configuration
#                                                     # processing in redis
#                                                     redis_pipeline = redis.pipeline()
#                                                     redis_pipeline.sadd(
#                                                         "autoconf-update-keys-to-process",
#                                                         msg["key"],
#                                                     )
#                                                     redis_pipeline.execute()
#                                                 except Exception:
#                                                     log.exception("exception")
#                                                 finally:
#                                                     lock.release()
#                                             else:
#                                                 with Producer(connection) as producer:
#                                                     producer.publish(
#                                                         msg,
#                                                         exchange=self.update_exchange,
#                                                         routing_key="update",
#                                                         serializer="ujson",
#                                                     )
#                                     else:
#                                         log.warning(
#                                             "Invalid format message: {}".format(msg)
#                                         )
#                                 except BaseException:
#                                     log.exception(
#                                         "Error when normalizing BGP message: {}".format(
#                                             msg
#                                         )
#                                     )
#                                 break
#                         except Exception:
#                             log.exception("exception")
#
#                 self.sio.on("exa_message", exabgp_msg)
#                 self.sio.emit("exa_subscribe", {"prefixes": self.prefixes})
#                 route_refresh_command_v4 = "announce route-refresh ipv4 unicast"
#                 self.sio.emit("route_command", {"command": route_refresh_command_v4})
#                 route_refresh_command_v6 = "announce route-refresh ipv6 unicast"
#                 self.sio.emit("route_command", {"command": route_refresh_command_v6})
#                 self.sio.wait()
#             except KeyboardInterrupt:
#                 self.exit()
#             except Exception:
#                 log.exception("exception")
#
#     def exit(self, signum, frame):
#         log.info("Exiting ExaBGP")
#         if self.autoconf:
#             autoconf_update_keys_to_process = set(
#                 map(
#                     lambda x: x.decode("ascii"),
#                     redis.smembers("autoconf-update-keys-to-process"),
#                 )
#             )
#
#             if len(autoconf_update_keys_to_process) == 0:
#                 # finish with sio now if there are not any pending autoconf updates
#                 if self.sio is not None:
#                     self.sio.disconnect()
#                 log.info("ExaBGP scheduled to exit...")
#         else:
#             if self.sio is not None:
#                 self.sio.disconnect()
#             if self.connection is not None:
#                 self.connection.release()
#             redis.set("exabgp_{}_running".format(self.host), 0)
#             log.info("ExaBGP exited")
#         self.should_stop = True
#
#
if __name__ == "__main__":
    # initiate ExaBGP tap service with REST
    exabgpTapService = ExaBGPTap()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_exabgp(exabgpTapService.shared_memory_manager_dict)
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # start REST within main process
    exabgpTapService.start_rest_app()
