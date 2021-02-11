import datetime
import json as classic_json
import multiprocessing as mp
import time
from typing import Dict
from typing import NoReturn

import redis
import requests
import ujson as json
from artemis_utils import get_hash
from artemis_utils import get_logger
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.constants import NOTIFIER_HOST
from artemis_utils.constants import PREFIXTREE_HOST
from artemis_utils.db import DB
from artemis_utils.envvars import BULK_TIMER
from artemis_utils.envvars import DB_HOST
from artemis_utils.envvars import DB_NAME
from artemis_utils.envvars import DB_PASS
from artemis_utils.envvars import DB_PORT
from artemis_utils.envvars import DB_USER
from artemis_utils.envvars import HISTORIC
from artemis_utils.envvars import RABBITMQ_URI
from artemis_utils.envvars import REDIS_HOST
from artemis_utils.envvars import REDIS_PORT
from artemis_utils.envvars import REST_PORT
from artemis_utils.envvars import WITHDRAWN_HIJACK_THRESHOLD
from artemis_utils.rabbitmq import create_exchange
from artemis_utils.rabbitmq import create_queue
from artemis_utils.redis import ping_redis
from artemis_utils.redis import purge_redis_eph_pers_keys
from artemis_utils.redis import redis_key
from artemis_utils.service import wait_data_worker_dependencies
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
    "monitors": mp.Lock(),
    "service_reconfiguring": mp.Lock(),
}

# global vars
TABLES = ["bgp_updates", "hijacks", "configs"]
VIEWS = ["view_configs", "view_bgpupdates", "view_hijacks"]
SERVICE_NAME = "database"
DATA_WORKER_DEPENDENCIES = [PREFIXTREE_HOST, NOTIFIER_HOST]


def save_config(wo_db, config_hash, yaml_config, raw_config, comment, config_timestamp):
    try:
        query = (
            "INSERT INTO configs (key, raw_config, time_modified, comment)"
            "VALUES (%s, %s, %s, %s);"
        )
        wo_db.execute(
            query,
            (
                config_hash,
                raw_config,
                datetime.datetime.fromtimestamp(config_timestamp),
                comment,
            ),
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


def retrieve_most_recent_raw_config(ro_db):
    return_msg = None
    try:
        entry = ro_db.execute(
            "SELECT key, raw_config, comment, time_modified from configs ORDER BY time_modified DESC LIMIT 1",
            fetch_one=True,
        )

        if entry:
            return_msg = {
                "key": entry[0],
                "raw_config": entry[1],
                "comment": entry[2],
                "time_modified": entry[3].timestamp(),
            }
    except Exception:
        log.exception("failed to retrieved most recent config in db")
    return return_msg


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
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        if config["timestamp"] > config_timestamp:
            shared_memory_locks["service_reconfiguring"].acquire()
            shared_memory_manager_dict["service_reconfiguring"] = True
            shared_memory_locks["service_reconfiguring"].release()

            incoming_config_timestamp = config["timestamp"]
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
                save_config(
                    wo_db,
                    config_hash,
                    config,
                    raw_config,
                    comment,
                    incoming_config_timestamp,
                )
            else:
                log.debug("database config is up-to-date")

            # extract monitors
            monitors = config.get("monitors", {})
            shared_memory_locks["monitors"].acquire()
            shared_memory_manager_dict["monitors"] = monitors
            shared_memory_locks["monitors"].release()

            # now that the conf is changed, get and store additional stats from prefixtree
            r = requests.get(
                "http://{}:{}/monitoredPrefixes".format(PREFIXTREE_HOST, REST_PORT)
            )
            shared_memory_locks["monitored_prefixes"].acquire()
            shared_memory_manager_dict["monitored_prefixes"] = r.json()[
                "monitored_prefixes"
            ]
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
            shared_memory_manager_dict["config_timestamp"] = incoming_config_timestamp
            shared_memory_locks["config_timestamp"].release()

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


class MonitorHandler(RequestHandler):
    """
    REST request handler for monitor information.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Simply provides the configured monitors (in the form of a JSON dict) to the requester
        """
        self.write({"monitors": self.shared_memory_manager_dict["monitors"]})


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.ro_db = DB(
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

    def get(self):
        """
        Simply provides the raw configuration stored in the DB
        (with timestamp, hash and comment) to the requester.
        Format:
        {
            "key": <string>,
            "raw_config": <string>,
            "comment": <string>,
            "time_modified": <timestamp>,
        }
        """
        most_recent_config = retrieve_most_recent_raw_config(self.ro_db)
        if most_recent_config:
            write_json = most_recent_config
            write_json["success"] = True
        else:
            write_json = {"success": False}
        self.write(write_json)

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
        :return: {"status" : <unconfigured|running|stopped><,reconfiguring>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
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
        try:
            with Connection(RABBITMQ_URI) as connection:
                with Producer(connection) as producer:
                    command_exchange = create_exchange("command", connection)
                    producer.publish(
                        "",
                        exchange=command_exchange,
                        routing_key="stop-{}".format(SERVICE_NAME),
                        serializer="ujson",
                    )
        except Exception:
            log.exception("exception")
        finally:
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
        self.shared_memory_manager_dict["service_reconfiguring"] = False
        self.shared_memory_manager_dict["monitored_prefixes"] = list()
        self.shared_memory_manager_dict["monitors"] = {}
        self.shared_memory_manager_dict["configured_prefix_count"] = 0
        self.shared_memory_manager_dict["config_timestamp"] = -1
        self.shared_memory_manager_dict["insert_bgp_entries"] = list()
        self.shared_memory_manager_dict["handle_bgp_withdrawals"] = list()
        self.shared_memory_manager_dict["handled_bgp_entries"] = list()
        self.shared_memory_manager_dict["outdate_hijacks"] = list()
        self.shared_memory_manager_dict["insert_hijacks_entries"] = {}

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
                    "/monitors",
                    MonitorHandler,
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


class DatabaseBulkUpdater:
    """
    Database bulk updater.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict

        # DB variables
        self.ro_db = DB(
            application_name="database-bulk-updater-readonly",
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
            application_name="database-bulk-updater-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )

        # EXCHANGES
        self.hijack_notification_exchange = create_exchange(
            "hijack-notification", connection, declare=True
        )

        # redis db
        self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

    def _insert_bgp_updates(self):
        shared_memory_locks["insert_bgp_entries"].acquire()
        num_of_entries = 0
        try:
            query = (
                "INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, "
                "timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES %s"
            )
            self.wo_db.execute_values(
                query,
                self.shared_memory_manager_dict["insert_bgp_entries"],
                page_size=1000,
            )
            num_of_entries = len(self.shared_memory_manager_dict["insert_bgp_entries"])
            self.shared_memory_manager_dict["insert_bgp_entries"] = []
        except Exception:
            log.exception("exception")
            num_of_entries = -1
        finally:
            shared_memory_locks["insert_bgp_entries"].release()
            return num_of_entries

    def _update_bgp_updates(self):
        num_of_updates = 0
        update_bgp_entries = set()
        timestamp_thres = time.time() - 7 * 24 * 60 * 60 if HISTORIC == "false" else 0
        timestamp_thres = datetime.datetime.fromtimestamp(timestamp_thres)
        # Update the BGP entries using the hijack messages
        handled_bgp_entries = set(
            self.shared_memory_manager_dict["handled_bgp_entries"]
        )
        for hijack_key in self.shared_memory_manager_dict["insert_hijacks_entries"]:
            for bgp_entry_to_update in self.shared_memory_manager_dict[
                "insert_hijacks_entries"
            ][hijack_key]["monitor_keys"]:
                num_of_updates += 1
                update_bgp_entries.add(
                    (hijack_key, bgp_entry_to_update, timestamp_thres)
                )
                # exclude handle bgp updates that point to same hijack as
                # this
                handled_bgp_entries.discard(bgp_entry_to_update)
        self.shared_memory_manager_dict["handled_bgp_entries"] = list(
            handled_bgp_entries
        )

        if update_bgp_entries:
            try:
                # update BGP updates either serially (if same hijack) or in parallel)
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

                # calculate new withdrawn peers seeing the new update announcements

                # get all bgp updates (announcements) keys that were just updated
                # plus the related hijack keys
                updated_hijack_keys = set(map(lambda x: x[0], update_bgp_entries))
                updated_bgp_update_keys = set(map(lambda x: x[1], update_bgp_entries))

                # get all handled hijack update entries of type 'A' that belong to this set
                # (ordered by DESC timestamp)
                query = (
                    "SELECT key, prefix, peer_asn, hijack_key, timestamp "
                    "FROM bgp_updates WHERE handled = true AND type = 'A'"
                    "AND hijack_key<>ARRAY[]::text[] "
                    "ORDER BY timestamp DESC"
                )
                ann_updates_entries = self.ro_db.execute(query)
                hijacks_to_ann_prefix_peer_timestamp = {}
                for entry in ann_updates_entries:
                    hijack_keys = entry[3]
                    for hijack_key in hijack_keys:
                        if (
                            hijack_key in updated_hijack_keys
                            and entry[0] in updated_bgp_update_keys
                        ):
                            prefix_peer = "{}-{}".format(entry[1], entry[2])
                            if hijack_key not in hijacks_to_ann_prefix_peer_timestamp:
                                hijacks_to_ann_prefix_peer_timestamp[hijack_key] = {}
                            # the following needs to take place only the first time the prefix-peer combo is encountered
                            if (
                                prefix_peer
                                not in hijacks_to_ann_prefix_peer_timestamp[hijack_key]
                            ):
                                hijacks_to_ann_prefix_peer_timestamp[hijack_key][
                                    prefix_peer
                                ] = (entry[4].timestamp(), entry[2])

                # get all handled hijack updates of type 'W' (ordered by DESC timestamp)
                query = (
                    "SELECT key, prefix, peer_asn, hijack_key, timestamp "
                    "FROM bgp_updates WHERE handled = true AND type = 'W'"
                    "AND hijack_key<>ARRAY[]::text[] "
                    "ORDER BY timestamp DESC"
                )
                wit_updates_entries = self.ro_db.execute(query)
                hijacks_to_wit_prefix_peer_timestamp = {}
                for entry in wit_updates_entries:
                    hijack_keys = entry[3]
                    for hijack_key in hijack_keys:
                        if hijack_key in updated_hijack_keys:
                            prefix_peer = "{}-{}".format(entry[1], entry[2])
                            if hijack_key not in hijacks_to_wit_prefix_peer_timestamp:
                                hijacks_to_wit_prefix_peer_timestamp[hijack_key] = {}
                            # the following needs to take place only the first time the prefix-peer combo is encountered
                            if (
                                prefix_peer
                                not in hijacks_to_wit_prefix_peer_timestamp[hijack_key]
                            ):
                                hijacks_to_wit_prefix_peer_timestamp[hijack_key][
                                    prefix_peer
                                ] = (entry[4].timestamp(), entry[2])

                # check what peers need to be removed from withdrawn sets
                remove_withdrawn_peers = set()
                for hijack_key in hijacks_to_ann_prefix_peer_timestamp:
                    if hijack_key in hijacks_to_wit_prefix_peer_timestamp:
                        for prefix_peer in hijacks_to_ann_prefix_peer_timestamp[
                            hijack_key
                        ]:
                            if (
                                prefix_peer
                                in hijacks_to_wit_prefix_peer_timestamp[hijack_key]
                            ):
                                if (
                                    hijacks_to_wit_prefix_peer_timestamp[hijack_key][
                                        prefix_peer
                                    ][0]
                                    < hijacks_to_ann_prefix_peer_timestamp[hijack_key][
                                        prefix_peer
                                    ][0]
                                ):
                                    remove_withdrawn_peers.add(
                                        (
                                            hijack_key,
                                            hijacks_to_ann_prefix_peer_timestamp[
                                                hijack_key
                                            ][prefix_peer][1],
                                        )
                                    )

                # execute query
                query = (
                    "UPDATE hijacks SET peers_withdrawn=array_remove(peers_withdrawn, data.v2::BIGINT) FROM "
                    "(VALUES %s) AS data (v1, v2) WHERE hijacks.key=data.v1"
                )
                self.wo_db.execute_values(
                    query, list(remove_withdrawn_peers), page_size=1000
                )

            except Exception:
                log.exception("exception")
                return -1

        num_of_updates += len(update_bgp_entries)
        update_bgp_entries.clear()

        # Update the BGP entries using the handled messages
        if self.shared_memory_manager_dict["handled_bgp_entries"]:
            try:
                query = "UPDATE bgp_updates SET handled=true FROM (VALUES %s) AS data (key) WHERE bgp_updates.key=data.key"
                self.wo_db.execute_values(
                    query,
                    self.shared_memory_manager_dict["handled_bgp_entries"],
                    page_size=1000,
                )
                num_of_updates += len(
                    self.shared_memory_manager_dict["handled_bgp_entries"]
                )
                self.shared_memory_manager_dict["handled_bgp_entries"] = []
            except Exception:
                log.exception(
                    "handled bgp entries {}".format(
                        len(self.shared_memory_manager_dict["handled_bgp_entries"])
                    )
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
            for key in self.shared_memory_manager_dict["insert_hijacks_entries"]:
                entry = (
                    key,  # key
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "type"
                    ],  # type
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "prefix"
                    ],  # prefix
                    # hijack_as
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "hijack_as"
                    ],
                    # num_peers_seen
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "num_peers_seen"
                    ],
                    # num_asns_inf
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "num_asns_inf"
                    ],
                    datetime.datetime.fromtimestamp(
                        self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                            "time_started"
                        ]
                    ),  # time_started
                    datetime.datetime.fromtimestamp(
                        self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                            "time_last"
                        ]
                    ),  # time_last
                    None,  # time_ended
                    None,  # mitigation_started
                    datetime.datetime.fromtimestamp(
                        self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                            "time_detected"
                        ]
                    ),  # time_detected
                    False,  # under_mitigation
                    True,  # active
                    False,  # resolved
                    False,  # ignored
                    False,  # withdrawn
                    False,  # dormant
                    # configured_prefix
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "configured_prefix"
                    ],
                    datetime.datetime.fromtimestamp(
                        self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                            "timestamp_of_config"
                        ]
                    ),  # timestamp_of_config
                    "",  # comment
                    # peers_seen
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "peers_seen"
                    ],
                    [],  # peers_withdrawn
                    # asns_inf
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "asns_inf"
                    ],
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "community_annotation"
                    ],
                    self.shared_memory_manager_dict["insert_hijacks_entries"][key][
                        "rpki_status"
                    ],
                )
                values.append(entry)

            self.wo_db.execute_values(query, values, page_size=1000)
            num_of_entries = len(
                self.shared_memory_manager_dict["insert_hijacks_entries"]
            )
            self.shared_memory_manager_dict["insert_hijacks_entries"] = {}
        except Exception:
            log.exception("exception")
            num_of_entries = -1

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
        for withdrawal in self.shared_memory_manager_dict["handle_bgp_withdrawals"]:
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
                                with Producer(self.connection) as producer:
                                    producer.publish(
                                        hijack,
                                        exchange=self.hijack_notification_exchange,
                                        routing_key="mail-log",
                                        retry=False,
                                        priority=1,
                                        serializer="ujson",
                                    )
                                    producer.publish(
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
        num_of_entries = len(self.shared_memory_manager_dict["handle_bgp_withdrawals"])
        self.shared_memory_manager_dict["handle_bgp_withdrawals"] = []
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

    def _handle_hijack_outdate(self):
        shared_memory_locks["outdate_hijacks"].acquire()
        if not self.shared_memory_manager_dict["outdate_hijacks"]:
            shared_memory_locks["outdate_hijacks"].release()
            return
        try:
            query = "UPDATE hijacks SET active=false, dormant=false, outdated=true FROM (VALUES %s) AS data (key) WHERE hijacks.key=data.key;"
            self.wo_db.execute_values(
                query,
                self.shared_memory_manager_dict["outdate_hijacks"],
                page_size=1000,
            )
            self.shared_memory_manager_dict["outdate_hijacks"] = []
        except Exception:
            log.exception("")
        finally:
            shared_memory_locks["outdate_hijacks"].release()

    def run(self):
        while True:
            # stop if parent is not running any more
            shared_memory_locks["data_worker"].acquire()
            if not self.shared_memory_manager_dict["data_worker_running"]:
                shared_memory_locks["data_worker"].release()
                break
            shared_memory_locks["data_worker"].release()
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
                log.error("flushing current state")
                shared_memory_locks["insert_bgp_entries"].acquire()
                shared_memory_locks["handle_bgp_withdrawals"].acquire()
                shared_memory_locks["handled_bgp_entries"].acquire()
                shared_memory_locks["outdate_hijacks"].acquire()
                shared_memory_locks["insert_hijacks_entries"].acquire()
                self.shared_memory_manager_dict["insert_bgp_entries"] = []
                self.shared_memory_manager_dict["handle_bgp_withdrawals"] = []
                self.shared_memory_manager_dict["handled_bgp_entries"] = []
                self.shared_memory_manager_dict["outdate_hijacks"] = []
                self.shared_memory_manager_dict["insert_hijacks_entries"] = {}
                shared_memory_locks["insert_bgp_entries"].release()
                shared_memory_locks["handle_bgp_withdrawals"].release()
                shared_memory_locks["handled_bgp_entries"].release()
                shared_memory_locks["outdate_hijacks"].release()
                shared_memory_locks["insert_hijacks_entries"].release()
            finally:
                time.sleep(BULK_TIMER)


class DatabaseDataWorker(ConsumerProducerMixin):
    """
    RabbitMQ Consumer/Producer for the Database Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.monitor_peers = 0

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
        # the first DB process that starts, bootstraps redis and blocks rest of replicas until complete
        if not self.redis.getset("redis-bootstrap", "1"):
            log.info("bootstrapping redis...")
            redis_pipeline = self.redis.pipeline()
            redis_pipeline.lpush("database-goahead", "1")
            redis_pipeline.blpop("database-goahead")
            redis_pipeline.execute()
            self.bootstrap_redis()
            log.info("redis bootstrapped...")
            self.redis.lpush("database-goahead", "1")
        else:
            while not self.redis.exists("database-goahead"):
                time.sleep(1)
            self.redis.blpop("database-goahead")
            self.redis.lpush("database-goahead", "1")
            log.info("redis already bootstrapped...")
        self.monitor_peers = self.redis.scard("peer-asns")

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

        log.info("setting up bulk updater process...")
        self.bulk_updater = DatabaseBulkUpdater(
            self.connection, self.shared_memory_manager_dict
        )
        mp.Process(target=self.bulk_updater.run).start()
        log.info("bulk updater set up")

        log.info("data worker initiated")

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
                accept=["ujson", "json"],
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
                accept=["ujson", "json"],
            ),
            Consumer(
                queues=[self.hijack_seen_queue],
                on_message=self.handle_hijack_seen,
                prefetch_count=1,
                accept=["ujson", "json"],
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
                accept=["ujson", "json"],
            ),
            Consumer(
                queues=[self.stop_queue],
                on_message=self.stop_consumer_loop,
                prefetch_count=100,
                accept=["ujson"],
            ),
        ]

    def handle_bgp_update(self, message):
        # log.debug('message: {}\npayload: {}'.format(message, message.payload))
        message.ack()
        msg_ = message.payload
        # prefix, key, origin_as, peer_asn, as_path, service, type, communities,
        # timestamp, hijack_key, handled, matched_prefix, orig_path

        if not self.redis.getset(msg_["key"], "1"):
            try:
                # discard old (older than 1.30 hour ago) timestamped BGP updates (may accumulate due to load)
                if (
                    HISTORIC == "false"
                    and msg_["timestamp"] < int(time.time()) - 90 * 60
                ):
                    return

                # discard BGP updates not matching any configured prefix any more
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
                insert_bgp_entries = self.shared_memory_manager_dict[
                    "insert_bgp_entries"
                ]
                insert_bgp_entries.append(value)
                self.shared_memory_manager_dict[
                    "insert_bgp_entries"
                ] = insert_bgp_entries
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
            handle_bgp_withdrawals = self.shared_memory_manager_dict[
                "handle_bgp_withdrawals"
            ]
            if value not in handle_bgp_withdrawals:
                handle_bgp_withdrawals.append(value)
            self.shared_memory_manager_dict[
                "handle_bgp_withdrawals"
            ] = handle_bgp_withdrawals
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
            if (raw["persistent_hijack_key"],) not in self.shared_memory_manager_dict[
                "outdate_hijacks"
            ]:
                outdate_hijacks = self.shared_memory_manager_dict["outdate_hijacks"]
                outdate_hijacks.append((raw["persistent_hijack_key"],))
                self.shared_memory_manager_dict["outdate_hijacks"] = outdate_hijacks
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

            insert_hijacks_entries = self.shared_memory_manager_dict[
                "insert_hijacks_entries"
            ]
            if key not in insert_hijacks_entries:
                # log.info('key {} at {}'.format(key, os.getpid()))
                insert_hijacks_entries[key] = {}
                insert_hijacks_entries[key]["prefix"] = msg_["prefix"]
                insert_hijacks_entries[key]["hijack_as"] = msg_["hijack_as"]
                insert_hijacks_entries[key]["type"] = msg_["type"]
                insert_hijacks_entries[key]["time_started"] = msg_["time_started"]
                insert_hijacks_entries[key]["time_last"] = msg_["time_last"]
                insert_hijacks_entries[key]["peers_seen"] = list(msg_["peers_seen"])
                insert_hijacks_entries[key]["asns_inf"] = list(msg_["asns_inf"])
                insert_hijacks_entries[key]["num_peers_seen"] = len(msg_["peers_seen"])
                insert_hijacks_entries[key]["num_asns_inf"] = len(msg_["asns_inf"])
                insert_hijacks_entries[key]["monitor_keys"] = set(msg_["monitor_keys"])
                insert_hijacks_entries[key]["time_detected"] = msg_["time_detected"]
                insert_hijacks_entries[key]["configured_prefix"] = msg_[
                    "configured_prefix"
                ]
                insert_hijacks_entries[key]["timestamp_of_config"] = msg_[
                    "timestamp_of_config"
                ]
                insert_hijacks_entries[key]["community_annotation"] = msg_[
                    "community_annotation"
                ]
                insert_hijacks_entries[key]["rpki_status"] = msg_["rpki_status"]
            else:
                insert_hijacks_entries[key]["time_started"] = min(
                    insert_hijacks_entries[key]["time_started"], msg_["time_started"]
                )
                insert_hijacks_entries[key]["time_last"] = max(
                    insert_hijacks_entries[key]["time_last"], msg_["time_last"]
                )
                insert_hijacks_entries[key]["peers_seen"] = list(msg_["peers_seen"])
                insert_hijacks_entries[key]["asns_inf"] = list(msg_["asns_inf"])
                insert_hijacks_entries[key]["num_peers_seen"] = len(msg_["peers_seen"])
                insert_hijacks_entries[key]["num_asns_inf"] = len(msg_["asns_inf"])
                insert_hijacks_entries[key]["monitor_keys"].update(msg_["monitor_keys"])
                insert_hijacks_entries[key]["community_annotation"] = msg_[
                    "community_annotation"
                ]
                insert_hijacks_entries[key]["rpki_status"] = msg_["rpki_status"]

            self.shared_memory_manager_dict[
                "insert_hijacks_entries"
            ] = insert_hijacks_entries
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
            handled_bgp_entries = self.shared_memory_manager_dict["handled_bgp_entries"]
            if key_ not in handled_bgp_entries:
                handled_bgp_entries.append(key_)
            self.shared_memory_manager_dict["handled_bgp_entries"] = handled_bgp_entries
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

            # get all ongoing hijack events
            query = (
                "SELECT time_started, time_last, peers_seen, "
                "asns_inf, key, prefix, hijack_as, type, time_detected, "
                "configured_prefix, timestamp_of_config, community_annotation, rpki_status "
                "FROM hijacks WHERE active = true"
            )
            ongoing_hijack_entries = self.ro_db.execute(query)
            ongoing_hijack_keys_to_entries = {}
            for entry in ongoing_hijack_entries:
                ongoing_hijack_keys_to_entries[entry[4]] = entry

            # get all hijack updates
            query = "SELECT key, hijack_key FROM bgp_updates WHERE handled = true AND hijack_key<>ARRAY[]::text[];"
            hijack_update_entries = self.ro_db.execute(query)
            ongoing_hijacks_to_updates = {}
            for entry in hijack_update_entries:
                hijack_keys = entry[1]
                for hijack_key in hijack_keys:
                    if hijack_key in ongoing_hijack_keys_to_entries:
                        if hijack_key not in ongoing_hijacks_to_updates:
                            ongoing_hijacks_to_updates[hijack_key] = set()
                        ongoing_hijacks_to_updates[hijack_key].add(entry[0])
            del hijack_update_entries

            # bootstrap hijack events in redis
            redis_pipeline = self.redis.pipeline()
            for entry in ongoing_hijack_entries:
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
                result["bgpupdate_keys"] = ongoing_hijacks_to_updates[entry[4]]

                redis_hijack_key = redis_key(entry[5], entry[6], entry[7])
                redis_pipeline.set(redis_hijack_key, json.dumps(result))
                redis_pipeline.sadd("persistent-keys", entry[4])
            redis_pipeline.execute()

            # bootstrap recent BGP updates
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

            # first get all hijack handled 'A' updates
            query = (
                "SELECT key, hijack_key, prefix, peer_asn, as_path FROM bgp_updates "
                "WHERE type = 'A' "
                "AND handled = true "
                "AND hijack_key<>ARRAY[]::text[];"
            )
            hijack_handled_ann_update_entries = self.ro_db.execute(query)
            hijack_handled_ann_update_keys_to_entries = {}
            for entry in hijack_handled_ann_update_entries:
                hijack_handled_ann_update_keys_to_entries[entry[0]] = entry

            # then map ongoing hijacks (we have them already from before) to those updates
            ongoing_hijacks_to_handled_ann_updates = {}
            for entry in hijack_handled_ann_update_entries:
                hijack_keys = entry[1]
                for hijack_key in hijack_keys:
                    if hijack_key in ongoing_hijack_keys_to_entries:
                        if hijack_key not in ongoing_hijacks_to_handled_ann_updates:
                            ongoing_hijacks_to_handled_ann_updates[hijack_key] = set()
                        ongoing_hijacks_to_handled_ann_updates[hijack_key].add(entry[0])

            # now store the combinations
            redis_pipeline = self.redis.pipeline()
            for hijack_key in ongoing_hijacks_to_handled_ann_updates:
                hijack_entry = ongoing_hijack_keys_to_entries[hijack_key]
                redis_hijack_key = redis_key(
                    hijack_entry[5], hijack_entry[6], hijack_entry[7]
                )
                for update_key in ongoing_hijacks_to_handled_ann_updates[hijack_key]:
                    update = hijack_handled_ann_update_keys_to_entries[update_key]
                    # store the origin, neighbor combination for this hijack BGP update
                    origin = None
                    neighbor = None
                    as_path = update[4]
                    if as_path:
                        origin = as_path[-1]
                    if len(as_path) > 1:
                        neighbor = as_path[-2]

                    redis_pipeline.sadd(
                        "hij_orig_neighb_{}".format(redis_hijack_key),
                        "{}_{}".format(origin, neighbor),
                    )

                    # store the prefix and peer asn for this hijack BGP update
                    redis_pipeline.sadd(
                        "prefix_{}_peer_{}_hijacks".format(update[2], update[3]),
                        redis_hijack_key,
                    )
                    redis_pipeline.sadd(
                        "hijack_{}_prefixes_peers".format(redis_hijack_key),
                        "{}_{}".format(update[2], update[3]),
                    )
            redis_pipeline.execute()

            # bootstrap seen monitor peers
            query = "SELECT DISTINCT peer_asn FROM bgp_updates"
            entries = self.ro_db.execute(query)

            redis_pipeline = self.redis.pipeline()
            for entry in entries:
                redis_pipeline.sadd("peer-asns", int(entry[0]))
            redis_pipeline.execute()

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
