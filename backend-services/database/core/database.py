import datetime
import json as classic_json
import multiprocessing as mp
import os
import threading
import time
from typing import Dict
from typing import NoReturn

import redis
import requests
import ujson as json
from artemis_utils import BULK_TIMER
from artemis_utils import DB_HOST
from artemis_utils import DB_NAME
from artemis_utils import DB_PASS
from artemis_utils import DB_PORT
from artemis_utils import DB_USER
from artemis_utils import get_hash
from artemis_utils import get_logger
from artemis_utils import HISTORIC
from artemis_utils import ping_redis
from artemis_utils import purge_redis_eph_pers_keys
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import redis_key
from artemis_utils import REDIS_PORT
from artemis_utils import WITHDRAWN_HIJACK_THRESHOLD
from artemis_utils.db_util import DB
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Producer
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

# logger
log = get_logger()

# shared memory object locks
shared_memory_locks = {
    "data_worker": mp.Lock(),
    "monitored_prefixes": mp.Lock(),
    "configured_prefix_count": mp.Lock(),
    "config_timestamp": mp.Lock(),
    "insert_bgp_entries": mp.Lock(),
    "handle_bgp_withdrawals": mp.Lock(),
    "handled_bgp_entries": mp.Lock(),
    "outdate_hijacks": mp.Lock(),
    "insert_hijacks_entries": mp.Lock(),
}

# global vars
TABLES = ["bgp_updates", "hijacks", "configs"]
VIEWS = ["view_configs", "view_bgpupdates", "view_hijacks"]
SERVICE_NAME = "database"
CONFIGURATION_HOST = "configuration"
PREFIXTREE_HOST = "prefixtree"
NOTIFIER_HOST = "notifier"
REST_PORT = int(os.getenv("REST_PORT", 3000))
DATA_WORKER_DEPENDENCIES = [PREFIXTREE_HOST, NOTIFIER_HOST]


# TODO: move this to util
def wait_data_worker_dependencies(data_worker_dependencies):
    while True:
        all_deps_met = True
        for service in data_worker_dependencies:
            try:
                r = requests.get("http://{}:{}/health".format(service, REST_PORT))
                status = True if r.json()["status"] == "running" else False
                if not status:
                    all_deps_met = False
                    break
            except Exception:
                all_deps_met = False
                break
        if all_deps_met:
            log.info("needed data workers started: {}".format(data_worker_dependencies))
            break
        log.info(
            "waiting for needed data workers to start: {}".format(
                data_worker_dependencies
            )
        )
        time.sleep(1)


def save_config(wo_db, config_hash, yaml_config, raw_config, comment):
    try:
        query = (
            "INSERT INTO configs (key, raw_config, time_modified, comment)"
            "VALUES (%s, %s, %s, %s);"
        )
        wo_db.execute(
            query, (config_hash, raw_config, datetime.datetime.now(), comment)
        )
    except Exception:
        log.exception("failed to save config in db")


def retrieve_most_recent_config_hash(ro_db):
    try:
        hash_ = ro_db.execute(
            "SELECT key from configs ORDER BY time_modified DESC LIMIT 1",
            fetch_one=True,
        )

        if isinstance(hash_, tuple):
            return hash_[0]
    except Exception:
        log.exception("failed to retrieved most recent config hash in db")
    return None


def store_monitored_prefixes_stat(wo_db, monitored_prefixes):
    try:
        wo_db.execute(
            "UPDATE stats SET monitored_prefixes=%s;", (len(monitored_prefixes),)
        )
    except Exception:
        log.exception("exception")


def store_configured_prefix_count_stat(wo_db, configured_prefix_count):
    try:
        wo_db.execute(
            "UPDATE stats SET configured_prefixes=%s;", (configured_prefix_count,)
        )
    except Exception:
        log.exception("exception")


def configure_database(msg, shared_memory_manager_dict):
    config = msg
    try:
        # DB variables
        ro_db = DB(
            application_name="database-rest-configuration-readonly",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            reconnect=True,
            autocommit=True,
            readonly=True,
        )
        wo_db = DB(
            application_name="database-rest-configuration-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

        # check newer config
        shared_memory_locks["config_timestamp"].acquire()
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        shared_memory_locks["config_timestamp"].release()
        if config["timestamp"] > config_timestamp:
            if "timestamp" in config:
                del config["timestamp"]
            raw_config = ""
            if "raw_config" in config:
                raw_config = config["raw_config"]
                del config["raw_config"]
            comment = ""
            if "comment" in config:
                comment = config["comment"]
                del config["comment"]
            config_hash = get_hash(raw_config)
            latest_config_in_db_hash = retrieve_most_recent_config_hash(ro_db)
            if config_hash != latest_config_in_db_hash:
                save_config(wo_db, config_hash, config, raw_config, comment)
            else:
                log.debug("database config is up-to-date")

            # now that the conf is changed, get and store additional stats from prefixtree
            r = requests.get(
                "http://{}:{}/monitoredPrefixes".format(PREFIXTREE_HOST, REST_PORT)
            )
            shared_memory_locks["monitored_prefixes"].acquire()
            shared_memory_manager_dict["monitored_prefixes"] = set(
                r.json()["monitored_prefixes"]
            )
            store_monitored_prefixes_stat(
                wo_db,
                monitored_prefixes=shared_memory_manager_dict["monitored_prefixes"],
            )
            shared_memory_locks["monitored_prefixes"].release()

            r = requests.get(
                "http://{}:{}/configuredPrefixCount".format(PREFIXTREE_HOST, REST_PORT)
            )
            shared_memory_locks["configured_prefix_count"].acquire()
            shared_memory_manager_dict["configured_prefix_count"] = r.json()[
                "configured_prefix_count"
            ]
            store_configured_prefix_count_stat(
                wo_db,
                configured_prefix_count=shared_memory_manager_dict[
                    "configured_prefix_count"
                ],
            )
            shared_memory_locks["configured_prefix_count"].release()

            shared_memory_locks["config_timestamp"].acquire()
            shared_memory_manager_dict["config_timestamp"] = config_timestamp
            shared_memory_locks["config_timestamp"].release()

        return {"success": True, "message": "configured"}
    except Exception:
        return {"success": False, "message": "error during service configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def post(self):
        """
        Configures database and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        try:
            msg = json.loads(self.request.body)
            self.write(configure_database(msg, self.shared_memory_manager_dict))
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
        :return: {"status" : <unconfigured|running|stopped>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
        shared_memory_locks["data_worker"].release()
        self.write({"status": status})


class ControlHandler(RequestHandler):
    """
    REST request handler for control commands.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def start_data_worker(self):
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            log.info("data worker already running")
            shared_memory_locks["data_worker"].release()
            return "already running"
        shared_memory_locks["data_worker"].release()
        mp.Process(target=self.run_data_worker_process).start()
        return "instructed to start"

    def run_data_worker_process(self):
        try:
            with Connection(RABBITMQ_URI) as connection:
                shared_memory_locks["data_worker"].acquire()
                data_worker = DatabaseDataWorker(
                    connection, self.shared_memory_manager_dict
                )
                self.shared_memory_manager_dict["data_worker_running"] = True
                shared_memory_locks["data_worker"].release()
                log.info("data worker started")
                data_worker.run()
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["data_worker"].acquire()
            self.shared_memory_manager_dict["data_worker_running"] = False
            shared_memory_locks["data_worker"].release()
            log.info("data worker stopped")

    @staticmethod
    def stop_data_worker():
        shared_memory_locks["data_worker"].acquire()
        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                command_exchange = create_exchange("command", connection)
                producer.publish(
                    "",
                    exchange=command_exchange,
                    routing_key="stop-{}".format(SERVICE_NAME),
                    serializer="ujson",
                )
        shared_memory_locks["data_worker"].release()
        message = "instructed to stop"
        return message

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
                message = self.start_data_worker()
                self.write({"success": True, "message": message})
            elif command == "stop":
                message = self.stop_data_worker()
                self.write({"success": True, "message": message})
            else:
                self.write({"success": False, "message": "unknown command"})
        except Exception:
            log.exception("Exception")
            self.write({"success": False, "message": "error during control"})


class HijackCommentHandler(RequestHandler):
    """
    REST request handler for hijack comments.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.wo_db = DB(
            application_name="database-rest-hijack-comment-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

    def post(self):
        """
        Receives a "hijack-comment" message and stores it in DB.
        :param message: {
            "key": <str>,
            "comment": <str>
        }
        :return: -
        """
        raw = json.loads(self.request.body)
        log.debug("payload: {}".format(raw))
        try:
            self.wo_db.execute(
                "UPDATE hijacks SET comment=%s WHERE key=%s;",
                (raw["comment"], raw["key"]),
            )
            self.write({"success": True, "message": ""})
        except Exception:
            self.write({"success": False, "message": "unknown error"})
            log.exception("{}".format(raw))


class HijackMultiActionHandler(RequestHandler):
    """
    REST request handler for multiple hijack actions.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.ro_db = DB(
            application_name="database-rest-hijack-multi-action-readonly",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            reconnect=True,
            autocommit=True,
            readonly=True,
        )
        self.wo_db = DB(
            application_name="database-rest-hijack-multi-action-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )
        self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

    def post(self):
        """
        Receives a "hijack-multi-action" message and applies the related actions in DB.
        :param message: {
            "keys": <list<str>>,
            "action": <str>
        }
        :return: -
        """
        raw = json.loads(self.request.body)
        log.debug("payload: {}".format(raw))
        seen_action = False
        ignore_action = False
        resolve_action = False
        delete_action = False
        try:
            if not raw["keys"]:
                query = None
            elif raw["action"] == "hijack_action_resolve":
                query = "UPDATE hijacks SET resolved=true, active=false, dormant=false, seen=true, time_ended=%s WHERE resolved=false AND ignored=false AND key=%s;"
                resolve_action = True
            elif raw["action"] == "hijack_action_ignore":
                query = "UPDATE hijacks SET ignored=true, active=false, dormant=false, seen=false WHERE ignored=false AND resolved=false AND key=%s;"
                ignore_action = True
            elif raw["action"] == "hijack_action_acknowledge":
                query = "UPDATE hijacks SET seen=true WHERE key=%s;"
                seen_action = True
            elif raw["action"] == "hijack_action_acknowledge_not":
                query = "UPDATE hijacks SET seen=false WHERE key=%s;"
                seen_action = True
            elif raw["action"] == "hijack_action_delete":
                query = "DELETE FROM hijacks WHERE key=%s;"
                delete_action = True
            else:
                raise BaseException("unreachable code reached")
        except Exception:
            log.exception("None action: {}".format(raw))
            query = None

        if not query:
            self.write({"success": False, "message": "unknown error"})
            return
        else:
            for hijack_key in raw["keys"]:
                try:
                    entries = self.ro_db.execute(
                        "SELECT prefix, hijack_as, type FROM hijacks WHERE key = %s;",
                        (hijack_key,),
                    )

                    if entries:
                        entry = entries[0]
                        redis_hijack_key = redis_key(
                            entry[0], entry[1], entry[2]  # prefix  # hijack_as  # type
                        )
                        if seen_action:
                            self.wo_db.execute(query, (hijack_key,))
                        elif ignore_action:
                            # if ongoing, clear redis
                            if self.redis.sismember("persistent-keys", hijack_key):
                                purge_redis_eph_pers_keys(
                                    self.redis, redis_hijack_key, hijack_key
                                )
                            self.wo_db.execute(query, (hijack_key,))
                        elif resolve_action:
                            # if ongoing, clear redis
                            if self.redis.sismember("persistent-keys", hijack_key):
                                purge_redis_eph_pers_keys(
                                    self.redis, redis_hijack_key, hijack_key
                                )
                            self.wo_db.execute(
                                query, (datetime.datetime.now(), hijack_key)
                            )
                        elif delete_action:
                            redis_hijack = self.redis.get(redis_hijack_key)
                            if self.redis.sismember("persistent-keys", hijack_key):
                                purge_redis_eph_pers_keys(
                                    self.redis, redis_hijack_key, hijack_key
                                )
                            log.debug(
                                "redis-entry for {}: {}".format(
                                    redis_hijack_key, redis_hijack
                                )
                            )
                            self.wo_db.execute(query, (hijack_key,))
                            if redis_hijack and classic_json.loads(
                                redis_hijack.decode("utf-8")
                            ).get("bgpupdate_keys", []):
                                log.debug("deleting hijack using cache for bgp updates")
                                redis_hijack = classic_json.loads(
                                    redis_hijack.decode("utf-8")
                                )
                                log.debug(
                                    "bgpupdate_keys {} for {}".format(
                                        redis_hijack["bgpupdate_keys"], redis_hijack
                                    )
                                )
                                self.wo_db.execute(
                                    "DELETE FROM bgp_updates WHERE %s = ANY(hijack_key) AND handled = true AND array_length(hijack_key,1) = 1 AND key = ANY(%s);",
                                    (hijack_key, list(redis_hijack["bgpupdate_keys"])),
                                )
                                self.wo_db.execute(
                                    "UPDATE bgp_updates SET hijack_key = array_remove(hijack_key, %s) WHERE handled = true AND key = ANY(%s);",
                                    (hijack_key, list(redis_hijack["bgpupdate_keys"])),
                                )
                            else:
                                log.debug(
                                    "deleting hijack by querying bgp updates database"
                                )
                                self.wo_db.execute(
                                    "DELETE FROM bgp_updates WHERE %s = ANY(hijack_key) AND array_length(hijack_key,1) = 1 AND handled = true;",
                                    (hijack_key,),
                                )
                                self.wo_db.execute(
                                    "UPDATE bgp_updates SET hijack_key = array_remove(hijack_key, %s) WHERE %s = ANY(hijack_key) AND handled = true;",
                                    (hijack_key, hijack_key),
                                )
                                log.debug(
                                    "bgpupdate_keys is empty for {}".format(
                                        redis_hijack
                                    )
                                )
                        else:
                            raise BaseException("unreachable code reached")

                except Exception as e:
                    log.exception("{}".format(raw))
                    self.write(
                        {
                            "success": False,
                            "message": "{}:{}".format(type(e).__name__, e.args),
                        }
                    )
                    return

        self.write({"success": True, "message": ""})


class Database:
    """
    Database REST Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["monitored_prefixes"] = set()
        self.shared_memory_manager_dict["configured_prefix_count"] = 0
        self.shared_memory_manager_dict["config_timestamp"] = -1

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
                (
                    "/hijackComment",
                    HijackCommentHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
                (
                    "/hijackMultiAction",
                    HijackMultiActionHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
            ]
        )

    def start_rest_app(self):
        app = self.make_rest_app()
        app.listen(REST_PORT)
        log.info("REST worker started and listening to port {}".format(REST_PORT))
        IOLoop.current().start()


class DatabaseDataWorker(ConsumerProducerMixin):
    """
    RabbitMQ Consumer/Producer for the Database Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.monitor_peers = 0
        self.insert_bgp_entries = []
        self.handle_bgp_withdrawals = set()
        self.handled_bgp_entries = set()
        self.outdate_hijacks = set()
        self.insert_hijacks_entries = {}
        self.bulk_timer_thread = None

        # DB variables
        self.ro_db = DB(
            application_name="database-data-worker-readonly",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            reconnect=True,
            autocommit=True,
            readonly=True,
        )
        self.wo_db = DB(
            application_name="database-data-worker-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

        # redis db
        self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
        ping_redis(self.redis)
        self.bootstrap_redis()

        # wait for other needed data workers to start
        wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

        # EXCHANGES
        self.update_exchange = create_exchange("bgp-update", connection, declare=True)
        self.hijack_exchange = create_exchange(
            "hijack-update", connection, declare=True
        )
        self.hijack_hashing = create_exchange(
            "hijack-hashing", connection, "x-consistent-hash", declare=True
        )
        self.handled_exchange = create_exchange(
            "handled-update", connection, declare=True
        )
        self.mitigation_exchange = create_exchange(
            "mitigation", connection, declare=True
        )
        self.hijack_notification_exchange = create_exchange(
            "hijack-notification", connection, declare=True
        )
        self.command_exchange = create_exchange("command", connection, declare=True)

        # QUEUES
        self.update_queue = create_queue(
            SERVICE_NAME,
            exchange=self.update_exchange,
            routing_key="update-with-prefix-node",
            priority=1,
        )
        self.withdraw_queue = create_queue(
            SERVICE_NAME,
            exchange=self.update_exchange,
            routing_key="withdraw",
            priority=1,
        )
        self.hijack_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_hashing,
            routing_key="1",
            priority=1,
            random=True,
        )
        self.hijack_ongoing_request_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_exchange,
            routing_key="ongoing-request",
            priority=1,
        )
        self.hijack_outdate_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_exchange,
            routing_key="outdate",
            priority=1,
        )
        self.hijack_resolve_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_exchange,
            routing_key="resolve",
            priority=2,
        )
        self.hijack_ignore_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_exchange,
            routing_key="ignore",
            priority=2,
        )
        self.handled_queue = create_queue(
            SERVICE_NAME,
            exchange=self.handled_exchange,
            routing_key="update",
            priority=1,
        )
        self.mitigate_queue = create_queue(
            SERVICE_NAME,
            exchange=self.mitigation_exchange,
            routing_key="mit-start",
            priority=2,
        )
        self.unmitigate_queue = create_queue(
            SERVICE_NAME,
            exchange=self.mitigation_exchange,
            routing_key="mit-end",
            priority=2,
        )
        self.hijack_seen_queue = create_queue(
            SERVICE_NAME, exchange=self.hijack_exchange, routing_key="seen", priority=2
        )
        self.hijack_delete_queue = create_queue(
            SERVICE_NAME,
            exchange=self.hijack_exchange,
            routing_key="delete",
            priority=2,
        )
        self.stop_queue = create_queue(
            "{}-{}".format(SERVICE_NAME, uuid()),
            exchange=self.command_exchange,
            routing_key="stop-{}".format(SERVICE_NAME),
            priority=1,
        )

        self.setup_bulk_update_timer()

    def get_consumers(self, Consumer, channel):
        return [
            Consumer(
                queues=[self.update_queue],
                on_message=self.handle_bgp_update,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_queue],
                on_message=self.handle_hijack_update,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.withdraw_queue],
                on_message=self.handle_withdraw_update,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.handled_queue],
                on_message=self.handle_handled_bgp_update,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_resolve_queue],
                on_message=self.handle_hijack_resolve,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.mitigate_queue],
                on_message=self.handle_mitigation_request,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.unmitigate_queue],
                on_message=self.handle_unmitigation_request,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_ignore_queue],
                on_message=self.handle_hijack_ignore,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_seen_queue],
                on_message=self.handle_hijack_seen,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_ongoing_request_queue],
                on_message=self.handle_hijack_ongoing_request,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_outdate_queue],
                on_message=self.handle_hijack_outdate,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.hijack_delete_queue],
                on_message=self.handle_hijack_delete,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.stop_queue],
                on_message=self.stop_consumer_loop,
                prefetch_count=100,
                accept=["ujson"],
            ),
        ]

    def setup_bulk_update_timer(self):
        """
        Timer for bulk operations (replaces deprecated db clock)
        """
        if self.should_stop:
            return
        self.bulk_timer_thread = threading.Timer(
            interval=BULK_TIMER, function=self._update_bulk
        )
        self.bulk_timer_thread.start()

    def handle_bgp_update(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        msg_ = message.payload
        # prefix, key, origin_as, peer_asn, as_path, service, type, communities,
        # timestamp, hijack_key, handled, matched_prefix, orig_path

        if not self.redis.getset(msg_["key"], "1"):
            try:
                best_match = msg_["prefix_node"]["prefix"]  # matched_prefix
                if not best_match:
                    return

                origin_as = -1
                if len(msg_["path"]) >= 1:
                    origin_as = msg_["path"][-1]

                value = (
                    msg_["prefix"],  # prefix
                    msg_["key"],  # key
                    origin_as,  # origin_as
                    msg_["peer_asn"],  # peer_asn
                    msg_["path"],  # as_path
                    msg_["service"],  # service
                    msg_["type"],  # type
                    json.dumps(
                        [(k["asn"], k["value"]) for k in msg_["communities"]]
                    ),  # communities
                    datetime.datetime.fromtimestamp((msg_["timestamp"])),  # timestamp
                    [],  # hijack_key
                    False,  # handled
                    best_match,
                    json.dumps(msg_["orig_path"]),  # orig_path
                )
                # insert all types of BGP updates
                # thread-safe access to update dict
                shared_memory_locks["insert_bgp_entries"].acquire()
                self.insert_bgp_entries.append(value)
                shared_memory_locks["insert_bgp_entries"].release()

                # register the monitor/peer ASN from whom we learned this BGP update
                self.redis.sadd("peer-asns", msg_["peer_asn"])
                redis_peer_asns = self.redis.scard("peer-asns")
                if redis_peer_asns != self.monitor_peers:
                    self.monitor_peers = redis_peer_asns
                    self.wo_db.execute(
                        "UPDATE stats SET monitor_peers=%s;", (self.monitor_peers,)
                    )
            except Exception:
                log.exception("{}".format(msg_))
            finally:
                # reset timer each time we hit the same BGP update
                self.redis.expire(msg_["key"], 2 * 60 * 60)

    def handle_withdraw_update(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        msg_ = message.payload
        shared_memory_locks["handle_bgp_withdrawals"].acquire()
        try:
            # update hijacks based on withdrawal messages
            value = (
                msg_["prefix"],  # prefix
                msg_["peer_asn"],  # peer_asn
                datetime.datetime.fromtimestamp((msg_["timestamp"])),  # timestamp
                msg_["key"],  # key
            )
            self.handle_bgp_withdrawals.add(value)
        except Exception:
            log.exception("{}".format(msg_))
        finally:
            shared_memory_locks["handle_bgp_withdrawals"].release()

    def handle_hijack_outdate(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        shared_memory_locks["outdate_hijacks"].acquire()
        try:
            raw = message.payload
            self.outdate_hijacks.add((raw["persistent_hijack_key"],))
        except Exception:
            log.exception("{}".format(message))
        finally:
            shared_memory_locks["outdate_hijacks"].release()

    def handle_hijack_update(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        msg_ = message.payload
        shared_memory_locks["insert_hijacks_entries"].acquire()
        try:
            key = msg_["key"]  # persistent hijack key

            if key not in self.insert_hijacks_entries:
                # log.info('key {} at {}'.format(key, os.getpid()))
                self.insert_hijacks_entries[key] = {}
                self.insert_hijacks_entries[key]["prefix"] = msg_["prefix"]
                self.insert_hijacks_entries[key]["hijack_as"] = msg_["hijack_as"]
                self.insert_hijacks_entries[key]["type"] = msg_["type"]
                self.insert_hijacks_entries[key]["time_started"] = msg_["time_started"]
                self.insert_hijacks_entries[key]["time_last"] = msg_["time_last"]
                self.insert_hijacks_entries[key]["peers_seen"] = list(
                    msg_["peers_seen"]
                )
                self.insert_hijacks_entries[key]["asns_inf"] = list(msg_["asns_inf"])
                self.insert_hijacks_entries[key]["num_peers_seen"] = len(
                    msg_["peers_seen"]
                )
                self.insert_hijacks_entries[key]["num_asns_inf"] = len(msg_["asns_inf"])
                self.insert_hijacks_entries[key]["monitor_keys"] = set(
                    msg_["monitor_keys"]
                )
                self.insert_hijacks_entries[key]["time_detected"] = msg_[
                    "time_detected"
                ]
                self.insert_hijacks_entries[key]["configured_prefix"] = msg_[
                    "configured_prefix"
                ]
                self.insert_hijacks_entries[key]["timestamp_of_config"] = msg_[
                    "timestamp_of_config"
                ]
                self.insert_hijacks_entries[key]["community_annotation"] = msg_[
                    "community_annotation"
                ]
                self.insert_hijacks_entries[key]["rpki_status"] = msg_["rpki_status"]
            else:
                self.insert_hijacks_entries[key]["time_started"] = min(
                    self.insert_hijacks_entries[key]["time_started"],
                    msg_["time_started"],
                )
                self.insert_hijacks_entries[key]["time_last"] = max(
                    self.insert_hijacks_entries[key]["time_last"], msg_["time_last"]
                )
                self.insert_hijacks_entries[key]["peers_seen"] = list(
                    msg_["peers_seen"]
                )
                self.insert_hijacks_entries[key]["asns_inf"] = list(msg_["asns_inf"])
                self.insert_hijacks_entries[key]["num_peers_seen"] = len(
                    msg_["peers_seen"]
                )
                self.insert_hijacks_entries[key]["num_asns_inf"] = len(msg_["asns_inf"])
                self.insert_hijacks_entries[key]["monitor_keys"].update(
                    msg_["monitor_keys"]
                )
                self.insert_hijacks_entries[key]["community_annotation"] = msg_[
                    "community_annotation"
                ]
                self.insert_hijacks_entries[key]["rpki_status"] = msg_["rpki_status"]
        except Exception:
            log.exception("{}".format(msg_))
        finally:
            shared_memory_locks["insert_hijacks_entries"].release()

    def handle_handled_bgp_update(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        shared_memory_locks["handled_bgp_entries"].acquire()
        try:
            key_ = (message.payload,)
            self.handled_bgp_entries.add(key_)
        except Exception:
            log.exception("{}".format(message))
        finally:
            shared_memory_locks["handled_bgp_entries"].release()

    def handle_hijack_ongoing_request(self, message):
        if not isinstance(message, dict):
            message.ack()
        try:
            results = []
            query = (
                "SELECT b.key, b.prefix, b.origin_as, b.as_path, b.type, b.peer_asn, "
                "b.communities, b.timestamp, b.service, b.matched_prefix, h.key, h.hijack_as, h.type "
                "FROM hijacks AS h LEFT JOIN bgp_updates AS b ON (h.key = ANY(b.hijack_key)) "
                "WHERE h.active = true AND b.handled=true"
            )

            entries = self.ro_db.execute(query)

            for entry in entries:
                results.append(
                    {
                        "key": entry[0],  # key
                        "prefix": entry[1],  # prefix
                        "origin_as": entry[2],  # origin ASN
                        "path": entry[3],  # as_path
                        "type": entry[4],  # type
                        "peer_asn": entry[5],  # peer_asn
                        "communities": entry[6],  # communities
                        "timestamp": entry[7].timestamp(),  # timestamp
                        "service": entry[8],  # service
                        "matched_prefix": entry[9],  # configured prefix
                        "hij_key": entry[10],
                        "hijack_as": entry[11],
                        "hij_type": entry[12],
                    }
                )

            if results:
                for result_bucket in [
                    results[i : i + 10] for i in range(0, len(results), 10)
                ]:
                    self.producer.publish(
                        result_bucket,
                        exchange=self.hijack_exchange,
                        routing_key="ongoing",
                        retry=False,
                        priority=1,
                        serializer="ujson",
                    )
        except Exception:
            log.exception("exception")

    def bootstrap_redis(self):
        try:

            # bootstrap ongoing hijack events
            query = (
                "SELECT time_started, time_last, peers_seen, "
                "asns_inf, key, prefix, hijack_as, type, time_detected, "
                "configured_prefix, timestamp_of_config, community_annotation, rpki_status "
                "FROM hijacks WHERE active = true"
            )

            entries = self.ro_db.execute(query)

            redis_pipeline = self.redis.pipeline()
            for entry in entries:
                result = {
                    "time_started": entry[0].timestamp(),
                    "time_last": entry[1].timestamp(),
                    "peers_seen": set(entry[2]),
                    "asns_inf": set(entry[3]),
                    "key": entry[4],
                    "prefix": entry[5],
                    "hijack_as": entry[6],
                    "type": entry[7],
                    "time_detected": entry[8].timestamp(),
                    "configured_prefix": entry[9],
                    "timestamp_of_config": entry[10].timestamp(),
                    "community_annotation": entry[11],
                    "rpki_status": entry[12],
                }

                subquery = "SELECT key FROM bgp_updates WHERE %s = ANY(hijack_key);"

                subentries = set(self.ro_db.execute(subquery, (entry[4],)))
                subentries = set(map(lambda x: x[0], subentries))
                log.debug(
                    "Adding bgpupdate_keys: {} for {} and {}".format(
                        subentries, redis_key(entry[5], entry[6], entry[7]), entry[4]
                    )
                )
                result["bgpupdate_keys"] = subentries

                redis_hijack_key = redis_key(entry[5], entry[6], entry[7])
                redis_pipeline.set(redis_hijack_key, json.dumps(result))
                redis_pipeline.sadd("persistent-keys", entry[4])
            redis_pipeline.execute()

            # bootstrap BGP updates
            query = (
                "SELECT key, timestamp FROM bgp_updates "
                "WHERE timestamp > NOW() - interval '2 hours' "
                "ORDER BY timestamp ASC"
            )

            entries = self.ro_db.execute(query)

            redis_pipeline = self.redis.pipeline()
            for entry in entries:
                expire = max(
                    int(entry[1].timestamp()) + 2 * 60 * 60 - int(time.time()), 60
                )
                redis_pipeline.set(entry[0], "1", ex=expire)
            redis_pipeline.execute()

            # bootstrap (origin, neighbor) AS-links of ongoing hijacks
            query = (
                "SELECT bgp_updates.prefix, bgp_updates.peer_asn, bgp_updates.as_path, "
                "hijacks.prefix, hijacks.hijack_as, hijacks.type FROM "
                "hijacks LEFT JOIN bgp_updates ON (hijacks.key = ANY(bgp_updates.hijack_key)) "
                "WHERE bgp_updates.type = 'A' "
                "AND hijacks.active = true "
                "AND bgp_updates.handled = true"
            )

            entries = self.ro_db.execute(query)

            redis_pipeline = self.redis.pipeline()
            for entry in entries:
                # store the origin, neighbor combination for this hijack BGP update
                origin = None
                neighbor = None
                as_path = entry[2]
                if as_path:
                    origin = as_path[-1]
                if len(as_path) > 1:
                    neighbor = as_path[-2]
                redis_hijack_key = redis_key(entry[3], entry[4], entry[5])
                redis_pipeline.sadd(
                    "hij_orig_neighb_{}".format(redis_hijack_key),
                    "{}_{}".format(origin, neighbor),
                )

                # store the prefix and peer asn for this hijack BGP update
                redis_pipeline.sadd(
                    "prefix_{}_peer_{}_hijacks".format(entry[0], entry[1]),
                    redis_hijack_key,
                )
                redis_pipeline.sadd(
                    "hijack_{}_prefixes_peers".format(redis_hijack_key),
                    "{}_{}".format(entry[0], entry[1]),
                )
            redis_pipeline.execute()

            # bootstrap seen monitor peers
            query = "SELECT DISTINCT peer_asn FROM bgp_updates"
            entries = self.ro_db.execute(query)

            redis_pipeline = self.redis.pipeline()
            for entry in entries:
                redis_pipeline.sadd("peer-asns", int(entry[0]))
            redis_pipeline.execute()
            self.monitor_peers = self.redis.scard("peer-asns")

            self.wo_db.execute(
                "UPDATE stats SET monitor_peers=%s;", (self.monitor_peers,)
            )

        except Exception:
            log.exception("exception")

    def handle_hijack_resolve(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            redis_hijack_key = redis_key(raw["prefix"], raw["hijack_as"], raw["type"])
            # if ongoing, clear redis
            if self.redis.sismember("persistent-keys", raw["key"]):
                purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])

            self.wo_db.execute(
                "UPDATE hijacks SET active=false, dormant=false, resolved=true, seen=true, time_ended=%s WHERE key=%s;",
                (datetime.datetime.now(), raw["key"]),
            )

        except Exception:
            log.exception("{}".format(raw))

    def handle_hijack_delete(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            redis_hijack_key = redis_key(raw["prefix"], raw["hijack_as"], raw["type"])
            redis_hijack = self.redis.get(redis_hijack_key)
            if self.redis.sismember("persistent-keys", raw["key"]):
                purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])

            log.debug("redis-entry for {}: {}".format(redis_hijack_key, redis_hijack))
            self.wo_db.execute("DELETE FROM hijacks WHERE key=%s;", (raw["key"],))
            if redis_hijack and classic_json.loads(redis_hijack.decode("utf-8")).get(
                "bgpupdate_keys", []
            ):
                log.debug("deleting hijack using cache for bgp updates")
                redis_hijack = classic_json.loads(redis_hijack.decode("utf-8"))
                log.debug(
                    "bgpupdate_keys {} for {}".format(
                        redis_hijack["bgpupdate_keys"], redis_hijack_key
                    )
                )
                self.wo_db.execute(
                    "DELETE FROM bgp_updates WHERE %s = ANY(hijack_key) AND handled = true AND array_length(hijack_key,1) = 1 AND key = ANY(%s);",
                    (raw["key"], list(redis_hijack["bgpupdate_keys"])),
                )
                self.wo_db.execute(
                    "UPDATE bgp_updates SET hijack_key = array_remove(hijack_key, %s) WHERE handled = true AND key = ANY(%s);",
                    (raw["key"], list(redis_hijack["bgpupdate_keys"])),
                )
            else:
                log.debug("deleting hijack by querying bgp updates database")
                self.wo_db.execute(
                    "DELETE FROM bgp_updates WHERE %s = ANY(hijack_key) AND array_length(hijack_key,1) = 1 AND handled = true;",
                    (raw["key"],),
                )
                self.wo_db.execute(
                    "UPDATE bgp_updates SET hijack_key = array_remove(hijack_key, %s) WHERE %s = ANY(hijack_key) AND handled = true;",
                    (raw["key"], raw["key"]),
                )

        except Exception:
            log.exception("{}".format(raw))

    def handle_mitigation_request(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            self.wo_db.execute(
                "UPDATE hijacks SET mitigation_started=%s, seen=true, under_mitigation=true WHERE key=%s;",
                (datetime.datetime.fromtimestamp(raw["time"]), raw["key"]),
            )
        except Exception:
            log.exception("{}".format(raw))

    def handle_unmitigation_request(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            self.wo_db.execute(
                "UPDATE hijacks SET under_mitigation=false WHERE key=%s;", (raw["key"],)
            )
        except Exception:
            log.exception("{}".format(raw))

    def handle_hijack_ignore(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            redis_hijack_key = redis_key(raw["prefix"], raw["hijack_as"], raw["type"])
            # if ongoing, clear redis
            if self.redis.sismember("persistent-keys", raw["key"]):
                purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])
            self.wo_db.execute(
                "UPDATE hijacks SET active=false, dormant=false, seen=false, ignored=true WHERE key=%s;",
                (raw["key"],),
            )
        except Exception:
            log.exception("{}".format(raw))

    def handle_hijack_seen(self, message):
        message.ack()
        raw = message.payload
        log.debug("payload: {}".format(raw))
        try:
            self.wo_db.execute(
                "UPDATE hijacks SET seen=%s WHERE key=%s;", (raw["state"], raw["key"])
            )
        except Exception:
            log.exception("{}".format(raw))

    def _insert_bgp_updates(self):
        shared_memory_locks["insert_bgp_entries"].acquire()
        num_of_entries = 0
        try:
            query = (
                "INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, "
                "timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES %s"
            )
            self.wo_db.execute_values(query, self.insert_bgp_entries, page_size=1000)
            num_of_entries = len(self.insert_bgp_entries)
            self.insert_bgp_entries.clear()
        except Exception:
            log.exception("exception")
            num_of_entries = -1
        finally:
            shared_memory_locks["insert_bgp_entries"].release()
            return num_of_entries

    def _handle_bgp_withdrawals(self):
        timestamp_thres = time.time() - 7 * 24 * 60 * 60 if HISTORIC == "false" else 0
        timestamp_thres = datetime.datetime.fromtimestamp(timestamp_thres)
        query = (
            "SELECT DISTINCT ON (hijacks.key) hijacks.peers_seen, hijacks.peers_withdrawn, "
            "hijacks.key, hijacks.hijack_as, hijacks.type, bgp_updates.timestamp, hijacks.time_last "
            "FROM hijacks LEFT JOIN bgp_updates ON (hijacks.key = ANY(bgp_updates.hijack_key)) "
            "WHERE bgp_updates.prefix = %s "
            "AND bgp_updates.type = 'A' "
            "AND bgp_updates.timestamp >= %s "
            "AND hijacks.active = true "
            "AND bgp_updates.peer_asn = %s "
            "AND bgp_updates.handled = true "
            "ORDER BY hijacks.key, bgp_updates.timestamp DESC"
        )
        update_normal_withdrawals = set()
        update_hijack_withdrawals = set()
        shared_memory_locks["handle_bgp_withdrawals"].acquire()
        for withdrawal in self.handle_bgp_withdrawals:
            try:
                # withdrawal -> 0: prefix, 1: peer_asn, 2: timestamp, 3:
                # key
                entries = self.ro_db.execute(
                    query, (withdrawal[0], timestamp_thres, withdrawal[1])
                )

                if not entries:
                    update_normal_withdrawals.add((withdrawal[3],))
                    continue
                for entry in entries:
                    # entry -> 0: peers_seen, 1: peers_withdrawn, 2:
                    # hij.key, 3: hij.as, 4: hij.type, 5: timestamp
                    # 6: time_last
                    update_hijack_withdrawals.add((entry[2], withdrawal[3]))
                    # update the bgpupdate_keys related to this hijack with withdrawals
                    redis_hijack_key = redis_key(withdrawal[0], entry[3], entry[4])
                    # to prevent detectors from working in parallel with hijack update
                    hijack = None
                    if self.redis.exists("{}token_active".format(redis_hijack_key)):
                        self.redis.set("{}token_active".format(redis_hijack_key), "1")
                    if self.redis.exists("{}token".format(redis_hijack_key)):
                        token = self.redis.blpop(
                            "{}token".format(redis_hijack_key), timeout=60
                        )
                        if not token:
                            log.info(
                                "Redis withdrawal addition encountered redis token timeout for hijack {}".format(
                                    entry[2]
                                )
                            )
                        hijack = self.redis.get(redis_hijack_key)
                        redis_pipeline = self.redis.pipeline()
                        if hijack:
                            hijack = classic_json.loads(hijack.decode("utf-8"))
                            hijack["bgpupdate_keys"] = list(
                                set(hijack["bgpupdate_keys"] + [withdrawal[3]])
                            )
                            redis_pipeline.set(redis_hijack_key, json.dumps(hijack))
                        redis_pipeline.lpush(
                            "{}token".format(redis_hijack_key), "token"
                        )
                        redis_pipeline.execute()
                    if entry[5] > withdrawal[2]:
                        continue
                    # matching withdraw with a hijack
                    if withdrawal[1] not in entry[1] and withdrawal[1] in entry[0]:
                        entry[1].append(withdrawal[1])
                        timestamp = max(withdrawal[2], entry[6])
                        # if a certain percentage of hijack 'A' peers see corresponding hijack 'W'
                        if len(entry[1]) >= int(
                            round(WITHDRAWN_HIJACK_THRESHOLD * len(entry[0]) / 100.0)
                        ):
                            # set hijack as withdrawn and delete from redis
                            if hijack:
                                hijack["end_tag"] = "withdrawn"
                            purge_redis_eph_pers_keys(
                                self.redis, redis_hijack_key, entry[2]
                            )
                            self.wo_db.execute(
                                "UPDATE hijacks SET active=false, dormant=false, resolved=false, withdrawn=true, time_ended=%s, "
                                "peers_withdrawn=%s, time_last=%s WHERE key=%s;",
                                (timestamp, entry[1], timestamp, entry[2]),
                            )

                            log.debug("withdrawn hijack {}".format(entry))
                            if hijack:
                                self.producer.publish(
                                    hijack,
                                    exchange=self.hijack_notification_exchange,
                                    routing_key="mail-log",
                                    retry=False,
                                    priority=1,
                                    serializer="ujson",
                                )
                                self.producer.publish(
                                    hijack,
                                    exchange=self.hijack_notification_exchange,
                                    routing_key="hij-log",
                                    retry=False,
                                    priority=1,
                                    serializer="ujson",
                                )
                        else:
                            # add withdrawal to hijack
                            self.wo_db.execute(
                                "UPDATE hijacks SET peers_withdrawn=%s, time_last=%s, dormant=false WHERE key=%s;",
                                (entry[1], timestamp, entry[2]),
                            )

                            log.debug("updating hijack {}".format(entry))
            except Exception:
                log.exception("exception")
        num_of_entries = len(self.handle_bgp_withdrawals)
        self.handle_bgp_withdrawals.clear()
        shared_memory_locks["handle_bgp_withdrawals"].release()

        try:
            update_hijack_withdrawals_dict = {}
            for update_hijack_withdrawal in update_hijack_withdrawals:
                hijack_key = update_hijack_withdrawal[0]
                withdrawal_key = update_hijack_withdrawal[1]
                if withdrawal_key not in update_hijack_withdrawals_dict:
                    update_hijack_withdrawals_dict[withdrawal_key] = set()
                update_hijack_withdrawals_dict[withdrawal_key].add(hijack_key)
            update_hijack_withdrawals_parallel = set()
            update_hijack_withdrawals_serial = set()
            for withdrawal_key in update_hijack_withdrawals_dict:
                if len(update_hijack_withdrawals_dict[withdrawal_key]) == 1:
                    for hijack_key in update_hijack_withdrawals_dict[withdrawal_key]:
                        update_hijack_withdrawals_parallel.add(
                            (hijack_key, withdrawal_key)
                        )
                else:
                    for hijack_key in update_hijack_withdrawals_dict[withdrawal_key]:
                        update_hijack_withdrawals_serial.add(
                            (hijack_key, withdrawal_key)
                        )

            # execute parallel execute values query
            query = (
                "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[data.v1]) "
                "FROM (VALUES %s) AS data (v1, v2) WHERE bgp_updates.key=data.v2"
            )
            self.wo_db.execute_values(
                query, list(update_hijack_withdrawals_parallel), page_size=1000
            )

            # execute serial execute_batch query
            query = (
                "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[%s]) "
                "WHERE bgp_updates.key=%s"
            )
            self.wo_db.execute_batch(
                query, list(update_hijack_withdrawals_serial), page_size=1000
            )
            update_hijack_withdrawals_parallel.clear()
            update_hijack_withdrawals_serial.clear()
            update_hijack_withdrawals_dict.clear()

            query = "UPDATE bgp_updates SET handled=true FROM (VALUES %s) AS data (key) WHERE bgp_updates.key=data.key"
            self.wo_db.execute_values(
                query, list(update_normal_withdrawals), page_size=1000
            )
        except Exception:
            log.exception("exception")

        return num_of_entries

    def _update_bgp_updates(self):
        num_of_updates = 0
        update_bgp_entries = set()
        timestamp_thres = time.time() - 7 * 24 * 60 * 60 if HISTORIC == "false" else 0
        timestamp_thres = datetime.datetime.fromtimestamp(timestamp_thres)
        # Update the BGP entries using the hijack messages
        for hijack_key in self.insert_hijacks_entries:
            for bgp_entry_to_update in self.insert_hijacks_entries[hijack_key][
                "monitor_keys"
            ]:
                num_of_updates += 1
                update_bgp_entries.add(
                    (hijack_key, bgp_entry_to_update, timestamp_thres)
                )
                # exclude handle bgp updates that point to same hijack as
                # this
                try:
                    self.handled_bgp_entries.discard(bgp_entry_to_update)
                except Exception:
                    log.exception("exception")

        if update_bgp_entries:
            try:
                query = (
                    "UPDATE hijacks SET peers_withdrawn=array_remove(peers_withdrawn, removed.peer_asn) FROM "
                    "(SELECT witann.key, witann.peer_asn FROM "
                    "(SELECT hij.key, wit.peer_asn, wit.timestamp AS wit_time, ann.timestamp AS ann_time FROM "
                    "((VALUES %s) AS data (v1, v2, v3) LEFT JOIN hijacks AS hij ON (data.v1=hij.key) "
                    "LEFT JOIN bgp_updates AS ann ON (data.v2=ann.key) "
                    "LEFT JOIN bgp_updates AS wit ON (hij.key=ANY(wit.hijack_key))) WHERE "
                    "ann.timestamp >= data.v3 AND wit.timestamp >= data.v3 AND "
                    "ann.type='A' AND wit.prefix=ann.prefix AND wit.peer_asn=ann.peer_asn AND wit.type='W' "
                    "ORDER BY wit_time DESC, hij.key LIMIT 1) AS witann WHERE witann.wit_time < witann.ann_time) "
                    "AS removed WHERE hijacks.key=removed.key"
                )
                self.wo_db.execute_values(
                    query, list(update_bgp_entries), page_size=1000
                )
                update_bgp_entries_dict = {}
                for update_bgp_entry in update_bgp_entries:
                    hijack_key = update_bgp_entry[0]
                    bgp_entry_to_update = update_bgp_entry[1]
                    if bgp_entry_to_update not in update_bgp_entries_dict:
                        update_bgp_entries_dict[bgp_entry_to_update] = set()
                    update_bgp_entries_dict[bgp_entry_to_update].add(hijack_key)
                update_bgp_entries_parallel = set()
                update_bgp_entries_serial = set()
                for bgp_entry_to_update in update_bgp_entries_dict:
                    if len(update_bgp_entries_dict[bgp_entry_to_update]) == 1:
                        for hijack_key in update_bgp_entries_dict[bgp_entry_to_update]:
                            update_bgp_entries_parallel.add(
                                (hijack_key, bgp_entry_to_update)
                            )
                    else:
                        for hijack_key in update_bgp_entries_dict[bgp_entry_to_update]:
                            update_bgp_entries_serial.add(
                                (hijack_key, bgp_entry_to_update)
                            )

                # execute parallel execute values query
                query = "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[data.v1]) FROM (VALUES %s) AS data (v1, v2) WHERE bgp_updates.key=data.v2"
                self.wo_db.execute_values(
                    query, list(update_bgp_entries_parallel), page_size=1000
                )

                # execute serial execute_batch query
                query = "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[%s]) WHERE bgp_updates.key=%s"
                self.wo_db.execute_batch(
                    query, list(update_bgp_entries_serial), page_size=1000
                )
                update_bgp_entries_parallel.clear()
                update_bgp_entries_serial.clear()
                update_bgp_entries_dict.clear()
            except Exception:
                log.exception("exception")
                return -1

        num_of_updates += len(update_bgp_entries)
        update_bgp_entries.clear()

        # Update the BGP entries using the handled messages
        if self.handled_bgp_entries:
            try:
                query = "UPDATE bgp_updates SET handled=true FROM (VALUES %s) AS data (key) WHERE bgp_updates.key=data.key"
                self.wo_db.execute_values(
                    query, self.handled_bgp_entries, page_size=1000
                )
                num_of_updates += len(self.handled_bgp_entries)
                self.handled_bgp_entries.clear()
            except Exception:
                log.exception(
                    "handled bgp entries {}".format(len(self.handled_bgp_entries))
                )
                num_of_updates = -1

        return num_of_updates

    def _insert_update_hijacks(self):

        try:
            query = (
                "INSERT INTO hijacks (key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, "
                "time_started, time_last, time_ended, mitigation_started, time_detected, under_mitigation, "
                "active, resolved, ignored, withdrawn, dormant, configured_prefix, timestamp_of_config, comment, peers_seen, peers_withdrawn, asns_inf, community_annotation, rpki_status) "
                "VALUES %s ON CONFLICT(key, time_detected) DO UPDATE SET num_peers_seen=excluded.num_peers_seen, num_asns_inf=excluded.num_asns_inf "
                ", time_started=LEAST(excluded.time_started, hijacks.time_started), time_last=GREATEST(excluded.time_last, hijacks.time_last), "
                "peers_seen=excluded.peers_seen, asns_inf=excluded.asns_inf, dormant=false, timestamp_of_config=excluded.timestamp_of_config, "
                "configured_prefix=excluded.configured_prefix, community_annotation=excluded.community_annotation, rpki_status=excluded.rpki_status"
            )

            values = []
            for key in self.insert_hijacks_entries:
                entry = (
                    key,  # key
                    self.insert_hijacks_entries[key]["type"],  # type
                    self.insert_hijacks_entries[key]["prefix"],  # prefix
                    # hijack_as
                    self.insert_hijacks_entries[key]["hijack_as"],
                    # num_peers_seen
                    self.insert_hijacks_entries[key]["num_peers_seen"],
                    # num_asns_inf
                    self.insert_hijacks_entries[key]["num_asns_inf"],
                    datetime.datetime.fromtimestamp(
                        self.insert_hijacks_entries[key]["time_started"]
                    ),  # time_started
                    datetime.datetime.fromtimestamp(
                        self.insert_hijacks_entries[key]["time_last"]
                    ),  # time_last
                    None,  # time_ended
                    None,  # mitigation_started
                    datetime.datetime.fromtimestamp(
                        self.insert_hijacks_entries[key]["time_detected"]
                    ),  # time_detected
                    False,  # under_mitigation
                    True,  # active
                    False,  # resolved
                    False,  # ignored
                    False,  # withdrawn
                    False,  # dormant
                    # configured_prefix
                    self.insert_hijacks_entries[key]["configured_prefix"],
                    datetime.datetime.fromtimestamp(
                        self.insert_hijacks_entries[key]["timestamp_of_config"]
                    ),  # timestamp_of_config
                    "",  # comment
                    # peers_seen
                    self.insert_hijacks_entries[key]["peers_seen"],
                    [],  # peers_withdrawn
                    # asns_inf
                    self.insert_hijacks_entries[key]["asns_inf"],
                    self.insert_hijacks_entries[key]["community_annotation"],
                    self.insert_hijacks_entries[key]["rpki_status"],
                )
                values.append(entry)

            self.wo_db.execute_values(query, values, page_size=1000)
            num_of_entries = len(self.insert_hijacks_entries)
            self.insert_hijacks_entries.clear()
        except Exception:
            log.exception("exception")
            num_of_entries = -1

        return num_of_entries

    def _handle_hijack_outdate(self):
        shared_memory_locks["outdate_hijacks"].acquire()
        if not self.outdate_hijacks:
            shared_memory_locks["outdate_hijacks"].release()
            return
        try:
            query = "UPDATE hijacks SET active=false, dormant=false, outdated=true FROM (VALUES %s) AS data (key) WHERE hijacks.key=data.key;"
            self.wo_db.execute_values(query, list(self.outdate_hijacks), page_size=1000)
            self.outdate_hijacks.clear()
        except Exception:
            log.exception("")
        finally:
            shared_memory_locks["outdate_hijacks"].release()

    def _update_bulk(self):
        try:
            inserts = self._insert_bgp_updates()
            shared_memory_locks["insert_hijacks_entries"].acquire()
            shared_memory_locks["handled_bgp_entries"].acquire()
            updates = self._update_bgp_updates()
            shared_memory_locks["handled_bgp_entries"].release()
            hijacks = self._insert_update_hijacks()
            shared_memory_locks["insert_hijacks_entries"].release()
            withdrawals = self._handle_bgp_withdrawals()
            self._handle_hijack_outdate()
            str_ = ""
            if inserts:
                str_ += "BGP Updates Inserted: {}\n".format(inserts)
            if updates:
                str_ += "BGP Updates Updated: {}\n".format(updates)
            if hijacks:
                str_ += "Hijacks Inserted: {}".format(hijacks)
            if withdrawals:
                str_ += "Withdrawals Handled: {}".format(withdrawals)
            if str_ != "":
                log.debug("{}".format(str_))
        except Exception:
            log.exception("exception")
        finally:
            self.setup_bulk_update_timer()

    def stop_consumer_loop(self, message: Dict) -> NoReturn:
        """
        Callback function that stop the current consumer loop
        """
        message.ack()
        self.should_stop = True


def main():
    # initiate database service with REST
    databaseService = Database()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_database(
            r.json(), databaseService.shared_memory_manager_dict
        )
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # start REST within main process
    databaseService.start_rest_app()


if __name__ == "__main__":
    main()
