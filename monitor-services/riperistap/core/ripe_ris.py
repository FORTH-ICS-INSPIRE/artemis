import multiprocessing as mp
import os
import signal
import time
from copy import deepcopy

import pytricia
import redis
import requests
import ujson as json
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.constants import DATABASE_HOST
from artemis_utils.constants import MAX_DATA_WORKER_WAIT_TIMEOUT
from artemis_utils.constants import PREFIXTREE_HOST
from artemis_utils.envvars import MON_TIMEOUT_LAST_BGP_UPDATE
from artemis_utils.envvars import RABBITMQ_URI
from artemis_utils.envvars import REDIS_HOST
from artemis_utils.envvars import REDIS_PORT
from artemis_utils.envvars import REST_PORT
from artemis_utils.envvars import RIS_ID
from artemis_utils.rabbitmq import create_exchange
from artemis_utils.redis import ping_redis
from artemis_utils.redis import RedisExpiryChecker
from artemis_utils.updates import key_generator
from artemis_utils.updates import MformatValidator
from artemis_utils.updates import normalize_msg_path
from kombu import Connection
from kombu import Producer
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
    "config_timestamp": mp.Lock(),
    "service_reconfiguring": mp.Lock(),
}

# global vars
update_to_type = {"announcements": "A", "withdrawals": "W"}
update_types = ["announcements", "withdrawals"]
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
SERVICE_NAME = "riperistap"


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
    data_worker_process = mp.Process(
        target=run_data_worker_process, args=(shared_memory_manager_dict,)
    )
    data_worker_process.start()
    shared_memory_locks["data_worker"].acquire()
    shared_memory_manager_dict["data_worker_process"] = data_worker_process.pid
    shared_memory_locks["data_worker"].release()
    return "instructed to start"


def run_data_worker_process(shared_memory_manager_dict):
    try:
        with Connection(RABBITMQ_URI) as connection:
            shared_memory_locks["data_worker"].acquire()
            data_worker = RipeRisTapDataWorker(connection, shared_memory_manager_dict)
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
    time_waiting = 0
    while True:
        if not shared_memory_manager_dict["data_worker_running"]:
            break
        time.sleep(1)
        time_waiting += 1
        if time_waiting == MAX_DATA_WORKER_WAIT_TIMEOUT:
            log.error(
                "timeout expired during stop-waiting, will kill process non-gracefully"
            )
            if shared_memory_manager_dict["data_worker_process"] is not None:
                os.kill(
                    shared_memory_manager_dict["data_worker_process"], signal.SIGKILL
                )
                shared_memory_locks["data_worker"].acquire()
                shared_memory_manager_dict["data_worker_process"] = None
                shared_memory_locks["data_worker"].release()
            shared_memory_locks["data_worker"].acquire()
            shared_memory_manager_dict["data_worker_running"] = False
            shared_memory_locks["data_worker"].release()
            return "killed"
    message = "instructed to stop"
    return message


def configure_ripe_ris(msg, shared_memory_manager_dict):
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

            # check if "riperis" is configured at all
            if "riperis" not in monitors:
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

            # calculate ripe ris hosts
            hosts = set(monitors["riperis"])
            if hosts == set([""]):
                hosts = set()
            shared_memory_locks["hosts"].acquire()
            shared_memory_manager_dict["hosts"] = list(hosts)
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
            "monitor_projects": <list>,
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
            self.write(configure_ripe_ris(msg, self.shared_memory_manager_dict))
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


class RipeRisTap:
    """
    RIPE RIS Tap REST Service.
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
        self.shared_memory_manager_dict["hosts"] = list()
        self.shared_memory_manager_dict["config_timestamp"] = -1
        self.shared_memory_manager_dict["data_worker_process"] = None

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


class RipeRisTapDataWorker:
    """
    RabbitMQ Producer for the Ripe RIS tap Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.prefixes = self.shared_memory_manager_dict["monitored_prefixes"]
        self.hosts = self.shared_memory_manager_dict["hosts"]

        # EXCHANGES
        self.update_exchange = create_exchange(
            "bgp-update", self.connection, declare=True
        )

        log.info("data worker initiated")

    def run(self):
        # update redis
        ping_redis(redis)
        redis.set("ris_seen_bgp_update", "1", ex=MON_TIMEOUT_LAST_BGP_UPDATE)

        # build monitored prefix tree
        prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
        for prefix in self.prefixes:
            ip_version = get_ip_version(prefix)
            prefix_tree[ip_version].insert(prefix, "")

        # set RIS suffix on connection
        ris_suffix = RIS_ID

        # main loop to process BGP updates
        validator = MformatValidator()
        with Producer(self.connection) as producer:
            while True:
                if not self.shared_memory_manager_dict["data_worker_should_run"]:
                    break
                try:
                    events = requests.get(
                        "https://ris-live.ripe.net/v1/stream/?format=json&client=artemis-{}".format(
                            ris_suffix
                        ),
                        stream=True,
                        timeout=10,
                    )
                    # http://docs.python-requests.org/en/latest/user/advanced/#streaming-requests
                    iterator = events.iter_lines()
                    next(iterator)
                    for data in iterator:
                        if not self.shared_memory_manager_dict[
                            "data_worker_should_run"
                        ]:
                            break
                        try:
                            parsed = json.loads(data)
                            msg = parsed["data"]
                            if "type" in parsed and parsed["type"] == "ris_error":
                                log.error(msg)
                            # also check if ris host is in the configuration
                            elif (
                                "type" in msg
                                and msg["type"] == "UPDATE"
                                and (not self.hosts or msg["host"] in self.hosts)
                            ):
                                norm_ris_msgs = self.normalize_ripe_ris(
                                    msg, prefix_tree
                                )
                                for norm_ris_msg in norm_ris_msgs:
                                    redis.set(
                                        "ris_seen_bgp_update",
                                        "1",
                                        ex=MON_TIMEOUT_LAST_BGP_UPDATE,
                                    )
                                    try:
                                        if validator.validate(norm_ris_msg):
                                            norm_path_msgs = normalize_msg_path(
                                                norm_ris_msg
                                            )
                                            for norm_path_msg in norm_path_msgs:
                                                key_generator(norm_path_msg)
                                                log.debug(norm_path_msg)
                                                producer.publish(
                                                    norm_path_msg,
                                                    exchange=self.update_exchange,
                                                    routing_key="update",
                                                    serializer="ujson",
                                                )
                                        else:
                                            log.debug(
                                                "Invalid format message: {}".format(msg)
                                            )
                                    except BaseException:
                                        log.exception("exception")
                                        log.error(
                                            "Error when normalizing BGP message: {}".format(
                                                norm_ris_msg
                                            )
                                        )
                        except Exception:
                            log.exception("exception")
                            log.error("exception message {}".format(data))
                    log.warning(
                        "Iterator ran out of data; the connection will be retried"
                    )
                except Exception:
                    log.exception("exception")
                    log.info(
                        "RIPE RIS Server closed connection. Restarting socket in 10 seconds.."
                    )
                    time.sleep(10)

    @staticmethod
    def normalize_ripe_ris(msg, prefix_tree):
        msgs = []
        if isinstance(msg, dict):
            msg["key"] = None  # initial placeholder before passing the validator
            if "community" in msg:
                msg["communities"] = [
                    {"asn": comm[0], "value": comm[1]} for comm in msg["community"]
                ]
                del msg["community"]
            if "host" in msg:
                msg["service"] = "ripe-ris|" + msg["host"]
                del msg["host"]
            if "peer_asn" in msg:
                msg["peer_asn"] = int(msg["peer_asn"])
            if "path" not in msg:
                msg["path"] = []
            if "timestamp" in msg:
                msg["timestamp"] = float(msg["timestamp"])
            if "type" in msg:
                del msg["type"]
            if "raw" in msg:
                del msg["raw"]
            if "origin" in msg:
                del msg["origin"]
            if "id" in msg:
                del msg["id"]
            if "announcements" in msg and "withdrawals" in msg:
                # need 2 separate messages
                # one for announcements
                msg_ann = deepcopy(msg)
                msg_ann["type"] = update_to_type["announcements"]
                prefixes = []
                for element in msg_ann["announcements"]:
                    if "prefixes" in element:
                        prefixes.extend(element["prefixes"])
                for prefix in prefixes:
                    ip_version = get_ip_version(prefix)
                    try:
                        if prefix in prefix_tree[ip_version]:
                            new_msg = deepcopy(msg_ann)
                            new_msg["prefix"] = prefix
                            del new_msg["announcements"]
                            del new_msg["withdrawals"]
                            msgs.append(new_msg)
                    except Exception:
                        log.exception("exception")
                # one for withdrawals
                msg_wit = deepcopy(msg)
                msg_wit["type"] = update_to_type["withdrawals"]
                msg_wit["path"] = []
                msg_wit["communities"] = []
                prefixes = msg_wit["withdrawals"]
                for prefix in prefixes:
                    ip_version = get_ip_version(prefix)
                    try:
                        if prefix in prefix_tree[ip_version]:
                            new_msg = deepcopy(msg_wit)
                            new_msg["prefix"] = prefix
                            del new_msg["announcements"]
                            del new_msg["withdrawals"]
                            msgs.append(new_msg)
                    except Exception:
                        log.exception("exception")
            else:
                for update_type in update_types:
                    if update_type in msg:
                        msg["type"] = update_to_type[update_type]
                        prefixes = []
                        for element in msg[update_type]:
                            if update_type == "announcements":
                                if "prefixes" in element:
                                    prefixes.extend(element["prefixes"])
                            elif update_type == "withdrawals":
                                prefixes.append(element)
                        for prefix in prefixes:
                            ip_version = get_ip_version(prefix)
                            try:
                                if prefix in prefix_tree[ip_version]:
                                    new_msg = deepcopy(msg)
                                    new_msg["prefix"] = prefix
                                    del new_msg[update_type]
                                    msgs.append(new_msg)
                            except Exception:
                                log.exception("exception")
        return msgs


def main():
    # initiate Ripe RIS tap service with REST
    ripeRisTapService = RipeRisTap()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_ripe_ris(
            r.json(), ripeRisTapService.shared_memory_manager_dict
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
        shared_memory_manager_dict=ripeRisTapService.shared_memory_manager_dict,
        monitor="ris",
        stop_data_worker_fun=stop_data_worker,
    )
    mp.Process(target=redis_checker.run).start()
    log.info("redis expiry checker set up")

    # start REST within main process
    ripeRisTapService.start_rest_app()


if __name__ == "__main__":
    main()
