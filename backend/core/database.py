import datetime
import logging
import os
import signal
import time
from xmlrpc.client import ServerProxy

import pytricia
import redis
import ujson as json
from artemis_utils import AUTO_RECOVER_PROCESS_STATE
from artemis_utils import BACKEND_SUPERVISOR_URI
from artemis_utils import DB_HOST
from artemis_utils import DB_NAME
from artemis_utils import DB_PASS
from artemis_utils import DB_PORT
from artemis_utils import DB_USER
from artemis_utils import flatten
from artemis_utils import get_hash
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import hijack_log_field_formatter
from artemis_utils import HISTORIC
from artemis_utils import ModulesState
from artemis_utils import MON_SUPERVISOR_URI
from artemis_utils import ping_redis
from artemis_utils import purge_redis_eph_pers_keys
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import redis_key
from artemis_utils import REDIS_PORT
from artemis_utils import search_worst_prefix
from artemis_utils import signal_loading
from artemis_utils import translate_asn_range
from artemis_utils import translate_rfc2622
from artemis_utils import WITHDRAWN_HIJACK_THRESHOLD
from artemis_utils.db_util import DB
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Consumer
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin

# import os

log = get_logger()
TABLES = ["bgp_updates", "hijacks", "configs"]
VIEWS = ["view_configs", "view_bgpupdates", "view_hijacks"]

hij_log = logging.getLogger("hijack_logger")
mail_log = logging.getLogger("mail_logger")
try:
    hij_log_filter = json.loads(os.getenv("HIJACK_LOG_FILTER", "[]"))
except Exception:
    log.exception("exception")
    hij_log_filter = []


class HijackLogFilter(logging.Filter):
    def filter(self, rec):
        if not hij_log_filter:
            return True
        for filter_entry in hij_log_filter:
            for filter_entry_key in filter_entry:
                if rec.__dict__[filter_entry_key] == filter_entry[filter_entry_key]:
                    return True
        return False


mail_log.addFilter(HijackLogFilter())
hij_log.addFilter(HijackLogFilter())


class Database:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            log.info("stopped")

    def exit(self, signum, frame):
        if self.worker:
            self.worker.ro_db.close()
            self.worker.wo_db.close()
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):
        def __init__(self, connection):
            self.module_name = "database"
            self.connection = connection
            self.prefix_tree = None
            self.monitored_prefixes = set()
            self.configured_prefix_count = 0
            self.monitor_peers = 0
            self.rules = None
            self.timestamp = -1
            self.insert_bgp_entries = []
            self.handle_bgp_withdrawals = set()
            self.handled_bgp_entries = set()
            self.outdate_hijacks = set()
            self.insert_hijacks_entries = {}

            # DB variables
            self.ro_db = DB(
                application_name="backend-readonly",
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
                application_name="backend-write",
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
            )

            try:
                self.wo_db.execute("TRUNCATE table process_states")

                query = (
                    "INSERT INTO process_states (name, running) "
                    "VALUES (%s, %s) ON CONFLICT(name) DO UPDATE SET running = excluded.running"
                )

                for ctx in {BACKEND_SUPERVISOR_URI, MON_SUPERVISOR_URI}:
                    if not ctx:
                        continue
                    server = ServerProxy(ctx)
                    processes = [
                        (x["name"], x["state"] == 20)
                        for x in server.supervisor.getAllProcessInfo()
                        if x["name"] != "listener"
                    ]
                    self.wo_db.execute_batch(query, processes)

            except Exception:
                log.exception("exception")

            try:
                query = (
                    "INSERT INTO intended_process_states (name, running) "
                    "VALUES (%s, %s) ON CONFLICT(name) DO NOTHING"
                )

                for ctx in {BACKEND_SUPERVISOR_URI, MON_SUPERVISOR_URI}:
                    if not ctx:
                        continue
                    server = ServerProxy(ctx)
                    processes = [
                        (x["group"], False)
                        for x in server.supervisor.getAllProcessInfo()
                        if x["group"] in ["monitor", "detection", "mitigation"]
                    ]

                    self.wo_db.execute_batch(query, processes)

            except Exception:
                log.exception("exception")

            # redis db
            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            ping_redis(self.redis)
            self.bootstrap_redis()

            # EXCHANGES
            self.config_exchange = create_exchange("config", connection)
            self.update_exchange = create_exchange(
                "bgp-update", connection, declare=True
            )
            self.hijack_exchange = create_exchange(
                "hijack-update", connection, declare=True
            )
            self.hijack_hashing = create_exchange(
                "hijack-hashing", connection, "x-consistent-hash", declare=True
            )
            self.handled_exchange = create_exchange("handled-update", connection)
            self.db_clock_exchange = create_exchange("db-clock", connection)
            self.mitigation_exchange = create_exchange("mitigation", connection)

            # QUEUES
            self.update_queue = create_queue(
                self.module_name,
                exchange=self.update_exchange,
                routing_key="update",
                priority=1,
            )
            self.withdraw_queue = create_queue(
                self.module_name,
                exchange=self.update_exchange,
                routing_key="withdraw",
                priority=1,
            )
            self.hijack_queue = create_queue(
                self.module_name,
                exchange=self.hijack_hashing,
                routing_key="1",
                priority=1,
                random=True,
            )
            self.hijack_ongoing_request_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="ongoing-request",
                priority=1,
            )
            self.hijack_outdate_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="outdate",
                priority=1,
            )
            self.hijack_resolve_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="resolve",
                priority=2,
            )
            self.hijack_ignore_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="ignore",
                priority=2,
            )
            self.handled_queue = create_queue(
                self.module_name,
                exchange=self.handled_exchange,
                routing_key="update",
                priority=1,
            )
            self.config_queue = create_queue(
                self.module_name,
                exchange=self.config_exchange,
                routing_key="notify",
                priority=2,
            )
            self.db_clock_queue = create_queue(
                self.module_name,
                exchange=self.db_clock_exchange,
                routing_key="pulse",
                priority=2,
                random=True,
            )
            self.mitigate_queue = create_queue(
                self.module_name,
                exchange=self.mitigation_exchange,
                routing_key="mit-start",
                priority=2,
            )
            self.hijack_seen_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="seen",
                priority=2,
            )
            self.hijack_delete_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="delete",
                priority=2,
            )

            # RPC QUEUES
            self.hijack_comment_queue = Queue(
                "database.rpc.hijack-comment",
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.hijack_multiple_action_queue = Queue(
                "database.rpc.hijack-multiple-action",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )

            signal_loading(self.module_name, True)
            self.config_request_rpc()
            signal_loading(self.module_name, False)

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
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
                    queues=[self.db_clock_queue],
                    on_message=self._scheduler_instruction,
                    prefetch_count=1,
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
                    on_message=self.handle_resolve_hijack,
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
                    queues=[self.hijack_ignore_queue],
                    on_message=self.handle_hijack_ignore_request,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.hijack_comment_queue],
                    on_message=self.handle_hijack_comment,
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
                    queues=[self.hijack_multiple_action_queue],
                    on_message=self.handle_hijack_multiple_action,
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
                    on_message=self.handle_delete_hijack,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
            ]

        def set_modules_to_intended_state(self):
            if AUTO_RECOVER_PROCESS_STATE != "true":
                return
            try:
                query = "SELECT name, running FROM intended_process_states"

                entries = self.ro_db.execute(query)
                modules_state = ModulesState()
                for entry in entries:
                    # entry[0] --> module name, entry[1] --> intended state
                    # start only intended modules (after making sure they are stopped
                    # to avoid stale entries)
                    if entry[1]:
                        log.info("Setting {} to start state.".format(entry[0]))
                        modules_state.call(entry[0], "stop")
                        time.sleep(1)
                        modules_state.call(entry[0], "start")
            except Exception:
                log.exception("exception")

        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            self.producer.publish(
                "",
                exchange="",
                routing_key="configuration.rpc.request",
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        "configuration.rpc.request",
                        durable=False,
                        max_priority=4,
                        consumer_arguments={"x-priority": 4},
                    ),
                    callback_queue,
                ],
                priority=4,
                serializer="ujson",
            )
            with Consumer(
                self.connection,
                on_message=self.handle_config_request_reply,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while self.rules is None:
                    self.connection.drain_events()

        def handle_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            message.ack()
            msg_ = message.payload
            # prefix, key, origin_as, peer_asn, as_path, service, type, communities,
            # timestamp, hijack_key, handled, matched_prefix, orig_path

            if not self.redis.getset(msg_["key"], "1"):
                best_match = (
                    self.find_best_prefix_match(msg_["prefix"]),
                )  # matched_prefix

                if not best_match:
                    return

                try:
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
                        datetime.datetime.fromtimestamp(
                            (msg_["timestamp"])
                        ),  # timestamp
                        [],  # hijack_key
                        False,  # handled
                        best_match,
                        json.dumps(msg_["orig_path"]),  # orig_path
                    )
                    # insert all types of BGP updates
                    self.insert_bgp_entries.append(value)

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
            # reset timer each time we hit the same BGP update
            self.redis.expire(msg_["key"], 2 * 60 * 60)

        def handle_withdraw_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            message.ack()
            msg_ = message.payload
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

        def handle_hijack_outdate(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            message.ack()
            try:
                raw = message.payload
                self.outdate_hijacks.add((raw["persistent_hijack_key"],))
            except Exception:
                log.exception("{}".format(message))

        def handle_hijack_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            message.ack()
            msg_ = message.payload
            try:
                key = msg_["key"]  # persistent hijack key
                if key not in self.insert_hijacks_entries:
                    # log.info('key {} at {}'.format(key, os.getpid()))
                    self.insert_hijacks_entries[key] = {}
                    self.insert_hijacks_entries[key]["prefix"] = msg_["prefix"]
                    self.insert_hijacks_entries[key]["hijack_as"] = msg_["hijack_as"]
                    self.insert_hijacks_entries[key]["type"] = msg_["type"]
                    self.insert_hijacks_entries[key]["time_started"] = msg_[
                        "time_started"
                    ]
                    self.insert_hijacks_entries[key]["time_last"] = msg_["time_last"]
                    self.insert_hijacks_entries[key]["peers_seen"] = list(
                        msg_["peers_seen"]
                    )
                    self.insert_hijacks_entries[key]["asns_inf"] = list(
                        msg_["asns_inf"]
                    )
                    self.insert_hijacks_entries[key]["num_peers_seen"] = len(
                        msg_["peers_seen"]
                    )
                    self.insert_hijacks_entries[key]["num_asns_inf"] = len(
                        msg_["asns_inf"]
                    )
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
                    self.insert_hijacks_entries[key]["rpki_status"] = msg_[
                        "rpki_status"
                    ]
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
                    self.insert_hijacks_entries[key]["asns_inf"] = list(
                        msg_["asns_inf"]
                    )
                    self.insert_hijacks_entries[key]["num_peers_seen"] = len(
                        msg_["peers_seen"]
                    )
                    self.insert_hijacks_entries[key]["num_asns_inf"] = len(
                        msg_["asns_inf"]
                    )
                    self.insert_hijacks_entries[key]["monitor_keys"].update(
                        msg_["monitor_keys"]
                    )
                    self.insert_hijacks_entries[key]["community_annotation"] = msg_[
                        "community_annotation"
                    ]
                    self.insert_hijacks_entries[key]["rpki_status"] = msg_[
                        "rpki_status"
                    ]
            except Exception:
                log.exception("{}".format(msg_))

        def handle_handled_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            message.ack()
            try:
                key_ = (message.payload,)
                self.handled_bgp_entries.add(key_)
            except Exception:
                log.exception("{}".format(message))

        def build_prefix_tree(self):
            log.info("Starting building database prefix tree...")
            self.prefix_tree = {
                "v4": pytricia.PyTricia(32),
                "v6": pytricia.PyTricia(128),
            }
            raw_prefix_count = 0
            for rule in self.rules:
                try:
                    rule_translated_origin_asn_set = set()
                    for asn in rule["origin_asns"]:
                        this_translated_asn_list = flatten(translate_asn_range(asn))
                        rule_translated_origin_asn_set.update(
                            set(this_translated_asn_list)
                        )
                    rule["origin_asns"] = list(rule_translated_origin_asn_set)
                    rule_translated_neighbor_set = set()
                    for asn in rule["neighbors"]:
                        this_translated_asn_list = flatten(translate_asn_range(asn))
                        rule_translated_neighbor_set.update(
                            set(this_translated_asn_list)
                        )
                    rule["neighbors"] = list(rule_translated_neighbor_set)
                    conf_obj = {
                        "origin_asns": rule["origin_asns"],
                        "neighbors": rule["neighbors"],
                    }
                    for prefix in rule["prefixes"]:
                        for translated_prefix in translate_rfc2622(prefix):
                            ip_version = get_ip_version(translated_prefix)
                            if self.prefix_tree[ip_version].has_key(translated_prefix):
                                node = self.prefix_tree[ip_version][translated_prefix]
                            else:
                                node = {
                                    "prefix": translated_prefix,
                                    "data": {"confs": []},
                                }
                                self.prefix_tree[ip_version].insert(
                                    translated_prefix, node
                                )
                            node["data"]["confs"].append(conf_obj)
                            raw_prefix_count += 1
                except Exception:
                    log.exception("Exception")
            log.info(
                "{} prefixes integrated in database prefix tree in total".format(
                    raw_prefix_count
                )
            )
            log.info("Finished building database prefix tree.")

            # calculate the monitored and configured prefixes
            log.info("Calculating configured and monitored prefixes in database...")
            self.monitored_prefixes = set()
            self.configured_prefix_count = 0
            for ip_version in self.prefix_tree:
                for prefix in self.prefix_tree[ip_version]:
                    self.configured_prefix_count += 1
                    monitored_prefix = search_worst_prefix(
                        prefix, self.prefix_tree[ip_version]
                    )
                    if monitored_prefix:
                        self.monitored_prefixes.add(monitored_prefix)
            try:
                self.wo_db.execute(
                    "UPDATE stats SET monitored_prefixes=%s, configured_prefixes=%s;",
                    (len(self.monitored_prefixes), self.configured_prefix_count),
                )
            except Exception:
                log.exception("exception")
            log.info("Calculated configured and monitored prefixes in database.")

        def find_best_prefix_match(self, prefix):
            ip_version = get_ip_version(prefix)
            if prefix in self.prefix_tree[ip_version]:
                return self.prefix_tree[ip_version].get_key(prefix)
            return None

        def handle_config_notify(self, message):
            message.ack()
            signal_loading(self.module_name, True)
            log.info("Reconfiguring database due to conf update...")

            log.debug("Message: {}\npayload: {}".format(message, message.payload))
            config = message.payload
            try:
                if config["timestamp"] > self.timestamp:
                    self.timestamp = config["timestamp"]
                    self.rules = config.get("rules", [])
                    self.build_prefix_tree()
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
                    self._save_config(config_hash, config, raw_config, comment)
            except Exception:
                log.exception("{}".format(config))

            log.info("Database initiated, configured and running.")
            signal_loading(self.module_name, False)

        def handle_config_request_reply(self, message):
            message.ack()
            signal_loading(self.module_name, True)
            log.info("Configuring database for the first time...")

            log.debug("Message: {}\npayload: {}".format(message, message.payload))
            config = message.payload
            try:
                if self.correlation_id == message.properties["correlation_id"]:
                    if config["timestamp"] > self.timestamp:
                        self.timestamp = config["timestamp"]
                        self.rules = config.get("rules", [])
                        self.build_prefix_tree()
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
                        latest_config_in_db_hash = (
                            self._retrieve_most_recent_config_hash()
                        )
                        if config_hash != latest_config_in_db_hash:
                            self._save_config(config_hash, config, raw_config, comment)
                        else:
                            log.debug("database config is up-to-date")
            except Exception:
                log.exception("{}".format(config))
            self.set_modules_to_intended_state()

            log.info("Database initiated, configured and running.")
            signal_loading(self.module_name, False)

        def handle_hijack_ongoing_request(self, message):
            message.ack()
            timestamp = message.payload

            # need redis to handle future case of multiple db processes
            last_timestamp = self.redis.get("last_handled_timestamp")
            if not last_timestamp or timestamp > float(last_timestamp):
                self.redis.set("last_handled_timestamp", timestamp)
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
                            subentries,
                            redis_key(entry[5], entry[6], entry[7]),
                            entry[4],
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

        def handle_resolve_hijack(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                # if ongoing, clear redis
                if self.redis.sismember("persistent-keys", raw["key"]):
                    purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])

                self.wo_db.execute(
                    "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, resolved=true, seen=true, time_ended=%s WHERE key=%s;",
                    (datetime.datetime.now(), raw["key"]),
                )

            except Exception:
                log.exception("{}".format(raw))

        def handle_delete_hijack(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                redis_hijack = self.redis.get(redis_hijack_key)
                if self.redis.sismember("persistent-keys", raw["key"]):
                    purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])

                log.debug(
                    "redis-entry for {}: {}".format(redis_hijack_key, redis_hijack)
                )
                self.wo_db.execute("DELETE FROM hijacks WHERE key=%s;", (raw["key"],))
                if redis_hijack and json.loads(redis_hijack).get("bgpupdate_keys", []):
                    log.debug("deleting hijack using cache for bgp updates")
                    redis_hijack = json.loads(redis_hijack)
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

        def handle_hijack_ignore_request(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                # if ongoing, clear redis
                if self.redis.sismember("persistent-keys", raw["key"]):
                    purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])
                self.wo_db.execute(
                    "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, seen=false, ignored=true WHERE key=%s;",
                    (raw["key"],),
                )
            except Exception:
                log.exception("{}".format(raw))

        def handle_hijack_comment(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.wo_db.execute(
                    "UPDATE hijacks SET comment=%s WHERE key=%s;",
                    (raw["comment"], raw["key"]),
                )

                self.producer.publish(
                    {"status": "accepted"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
            except Exception:
                self.producer.publish(
                    {"status": "rejected"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
                log.exception("{}".format(raw))

        def handle_hijack_seen(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.wo_db.execute(
                    "UPDATE hijacks SET seen=%s WHERE key=%s;",
                    (raw["state"], raw["key"]),
                )
            except Exception:
                log.exception("{}".format(raw))

        def handle_hijack_multiple_action(self, message):
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            query = None
            seen_action = False
            ignore_action = False
            resolve_action = False
            delete_action = False
            try:
                if not raw["keys"]:
                    query = None
                elif raw["action"] == "hijack_action_resolve":
                    query = "UPDATE hijacks SET resolved=true, active=false, dormant=false, under_mitigation=false, seen=true, time_ended=%s WHERE resolved=false AND ignored=false AND key=%s;"
                    resolve_action = True
                elif raw["action"] == "hijack_action_ignore":
                    query = "UPDATE hijacks SET ignored=true, active=false, dormant=false, under_mitigation=false, seen=false WHERE ignored=false AND resolved=false AND key=%s;"
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
                self.producer.publish(
                    {"status": "rejected"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
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
                                entry[0],
                                entry[1],
                                entry[2],  # prefix  # hijack_as  # type
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
                                if redis_hijack and json.loads(redis_hijack).get(
                                    "bgpupdate_keys", []
                                ):
                                    log.debug(
                                        "deleting hijack using cache for bgp updates"
                                    )
                                    redis_hijack = json.loads(redis_hijack)
                                    log.debug(
                                        "bgpupdate_keys {} for {}".format(
                                            redis_hijack["bgpupdate_keys"], redis_hijack
                                        )
                                    )
                                    self.wo_db.execute(
                                        "DELETE FROM bgp_updates WHERE %s = ANY(hijack_key) AND handled = true AND array_length(hijack_key,1) = 1 AND key = ANY(%s);",
                                        (
                                            hijack_key,
                                            list(redis_hijack["bgpupdate_keys"]),
                                        ),
                                    )
                                    self.wo_db.execute(
                                        "UPDATE bgp_updates SET hijack_key = array_remove(hijack_key, %s) WHERE handled = true AND key = ANY(%s);",
                                        (
                                            hijack_key,
                                            list(redis_hijack["bgpupdate_keys"]),
                                        ),
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
                        self.producer.publish(
                            {
                                "status": "rejected",
                                "reason": "{}:{}".format(type(e).__name__, e.args),
                            },
                            exchange="",
                            routing_key=message.properties["reply_to"],
                            correlation_id=message.properties["correlation_id"],
                            retry=True,
                            priority=4,
                            serializer="ujson",
                        )

            self.producer.publish(
                {"status": "accepted"},
                exchange="",
                routing_key=message.properties["reply_to"],
                correlation_id=message.properties["correlation_id"],
                retry=True,
                priority=4,
                serializer="ujson",
            )

        def _insert_bgp_updates(self):
            try:
                query = (
                    "INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, "
                    "timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES %s"
                )
                self.wo_db.execute_values(
                    query, self.insert_bgp_entries, page_size=1000
                )
            except Exception:
                log.exception("exception")
                return -1
            finally:
                num_of_entries = len(self.insert_bgp_entries)
                self.insert_bgp_entries.clear()
            return num_of_entries

        def _handle_bgp_withdrawals(self):
            timestamp_thres = (
                time.time() - 7 * 24 * 60 * 60 if HISTORIC == "false" else 0
            )
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
                            self.redis.set(
                                "{}token_active".format(redis_hijack_key), "1"
                            )
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
                                hijack = json.loads(hijack)
                                hijack["bgpupdate_keys"] = set(
                                    hijack["bgpupdate_keys"] + [withdrawal[3]]
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
                                round(
                                    WITHDRAWN_HIJACK_THRESHOLD * len(entry[0]) / 100.0
                                )
                            ):
                                # set hijack as withdrawn and delete from redis
                                if hijack:
                                    hijack["end_tag"] = "withdrawn"
                                purge_redis_eph_pers_keys(
                                    self.redis, redis_hijack_key, entry[2]
                                )
                                self.wo_db.execute(
                                    "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, resolved=false, withdrawn=true, time_ended=%s, "
                                    "peers_withdrawn=%s, time_last=%s WHERE key=%s;",
                                    (timestamp, entry[1], timestamp, entry[2]),
                                )

                                log.debug("withdrawn hijack {}".format(entry))
                                if hijack:
                                    mail_log.info(
                                        "{}".format(
                                            json.dumps(
                                                hijack_log_field_formatter(hijack),
                                                indent=4,
                                            )
                                        ),
                                        extra={
                                            "community_annotation": hijack.get(
                                                "community_annotation", "NA"
                                            )
                                        },
                                    )
                                    hij_log.info(
                                        "{}".format(
                                            json.dumps(
                                                hijack_log_field_formatter(hijack)
                                            )
                                        ),
                                        extra={
                                            "community_annotation": hijack.get(
                                                "community_annotation", "NA"
                                            )
                                        },
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
                        for hijack_key in update_hijack_withdrawals_dict[
                            withdrawal_key
                        ]:
                            update_hijack_withdrawals_parallel.add(
                                (hijack_key, withdrawal_key)
                            )
                    else:
                        for hijack_key in update_hijack_withdrawals_dict[
                            withdrawal_key
                        ]:
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

            num_of_entries = len(self.handle_bgp_withdrawals)
            self.handle_bgp_withdrawals.clear()
            return num_of_entries

        def _update_bgp_updates(self):
            num_of_updates = 0
            update_bgp_entries = set()
            timestamp_thres = (
                time.time() - 7 * 24 * 60 * 60 if HISTORIC == "false" else 0
            )
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
                    self.handled_bgp_entries.discard(bgp_entry_to_update)

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
                            for hijack_key in update_bgp_entries_dict[
                                bgp_entry_to_update
                            ]:
                                update_bgp_entries_parallel.add(
                                    (hijack_key, bgp_entry_to_update)
                                )
                        else:
                            for hijack_key in update_bgp_entries_dict[
                                bgp_entry_to_update
                            ]:
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
                except Exception:
                    log.exception(
                        "handled bgp entries {}".format(self.handled_bgp_entries)
                    )
                    return -1

            num_of_updates += len(self.handled_bgp_entries)
            self.handled_bgp_entries.clear()
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
            except Exception:
                log.exception("exception")
                return -1

            num_of_entries = len(self.insert_hijacks_entries)
            self.insert_hijacks_entries.clear()
            return num_of_entries

        def _handle_hijack_outdate(self):
            if not self.outdate_hijacks:
                return
            try:
                query = "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, outdated=true FROM (VALUES %s) AS data (key) WHERE hijacks.key=data.key;"
                self.wo_db.execute_values(
                    query, list(self.outdate_hijacks), page_size=1000
                )
                self.outdate_hijacks.clear()
            except Exception:
                log.exception("")

        def _update_bulk(self):
            inserts, updates, hijacks, withdrawals = (
                self._insert_bgp_updates(),
                self._update_bgp_updates(),
                self._insert_update_hijacks(),
                self._handle_bgp_withdrawals(),
            )
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

        def _scheduler_instruction(self, message):
            message.ack()
            msg_ = message.payload
            if msg_["op"] == "bulk_operation":
                self._update_bulk()
            # elif msg_["op"] == "send_unhandled":
            #     self._retrieve_unhandled(msg_["amount"])
            else:
                log.warning(
                    "Received uknown instruction from scheduler: {}".format(msg_)
                )

        def _save_config(self, config_hash, yaml_config, raw_config, comment):
            try:
                log.debug("Config Store..")
                query = (
                    "INSERT INTO configs (key, raw_config, time_modified, comment)"
                    "VALUES (%s, %s, %s, %s);"
                )
                self.wo_db.execute(
                    query, (config_hash, raw_config, datetime.datetime.now(), comment)
                )
            except Exception:
                log.exception("failed to save config in db")

        def _retrieve_most_recent_config_hash(self):
            try:
                hash_ = self.ro_db.execute(
                    "SELECT key from configs ORDER BY time_modified DESC LIMIT 1",
                    fetch_one=True,
                )

                if isinstance(hash_, tuple):
                    return hash_[0]
            except Exception:
                log.exception("failed to retrieved most recent config hash in db")
            return None


def run():
    service = Database()
    service.run()


if __name__ == "__main__":
    run()
