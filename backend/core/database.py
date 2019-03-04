import datetime
import hashlib
import json
import os
import pickle
import signal
import time
from xmlrpc.client import ServerProxy

import psycopg2.extras
import radix
import redis
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from utils import flatten
from utils import get_logger
from utils import get_ro_cursor
from utils import get_wo_cursor
from utils import purge_redis_eph_pers_keys
from utils import RABBITMQ_URI
from utils import redis_key
from utils import SUPERVISOR_HOST
from utils import SUPERVISOR_PORT
from utils import translate_rfc2622

log = get_logger()
TABLES = ["bgp_updates", "hijacks", "configs"]
VIEWS = ["view_configs", "view_bgpupdates", "view_hijacks"]


class Database:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def connectDb(self):
        _db_conn = None
        time_sleep_connection_retry = 5
        while not _db_conn:
            try:
                _db_name = os.getenv("DATABASE_NAME", "artemis_db")
                _user = os.getenv("DATABASE_USER", "artemis_user")
                _host = os.getenv("DATABASE_HOST", "postgres")
                _password = os.getenv("DATABASE_PASSWORD", "Art3m1s")

                _db_conn = psycopg2.connect(
                    dbname=_db_name, user=_user, host=_host, password=_password
                )

            except Exception:
                log.exception("exception")
                time.sleep(time_sleep_connection_retry)
            finally:
                log.debug("PostgreSQL DB created/connected..")

        return _db_conn

    def run(self):
        # read-only connection
        ro_conn = self.connectDb()
        ro_conn.set_session(autocommit=True, readonly=True)
        # write-only connection
        wo_conn = self.connectDb()
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection, ro_conn, wo_conn)
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            log.info("stopped")
            ro_conn.close()
            wo_conn.close()

    def exit(self, signum, frame):
        if self.worker:
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):
        def __init__(self, connection, ro_conn, wo_conn):
            self.connection = connection
            self.prefix_tree = None
            self.rules = None
            self.timestamp = -1
            self.insert_bgp_entries = []
            self.handle_bgp_withdrawals = set()
            self.handled_bgp_entries = set()
            self.outdate_hijacks = set()
            self.insert_hijacks_entries = {}

            # DB variables
            self.ro_conn = ro_conn
            self.wo_conn = wo_conn

            try:
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute("TRUNCATE table process_states")

                server = ServerProxy(
                    "http://{}:{}/RPC2".format(SUPERVISOR_HOST, SUPERVISOR_PORT)
                )
                query = (
                    "INSERT INTO process_states (name, running) "
                    "VALUES (%s, %s) ON CONFLICT(name) DO UPDATE SET running = excluded.running"
                )
                processes = [
                    (x["name"], x["state"] == 20)
                    for x in server.supervisor.getAllProcessInfo()
                    if x["name"] != "listener"
                ]

                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_batch(db_cur, query, processes)

            except Exception:
                log.exception("exception")

            # redis db
            self.redis = redis.Redis(host="localhost", port=6379)
            self.bootstrap_redis()

            # EXCHANGES
            self.config_exchange = Exchange(
                "config",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.update_exchange = Exchange(
                "bgp-update",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.update_exchange.declare()

            self.hijack_exchange = Exchange(
                "hijack-update",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.hijack_exchange.declare()

            self.hijack_hashing = Exchange(
                "hijack-hashing",
                channel=connection,
                type="x-consistent-hash",
                durable=False,
                delivery_mode=1,
            )
            self.hijack_hashing.declare()

            self.handled_exchange = Exchange(
                "handled-update", type="direct", durable=False, delivery_mode=1
            )
            self.db_clock_exchange = Exchange(
                "db-clock", type="direct", durable=False, delivery_mode=1
            )
            self.mitigation_exchange = Exchange(
                "mitigation", type="direct", durable=False, delivery_mode=1
            )

            # QUEUES
            self.update_queue = Queue(
                "db-bgp-update",
                exchange=self.update_exchange,
                routing_key="update",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.withdraw_queue = Queue(
                "db-withdraw-update",
                exchange=self.update_exchange,
                routing_key="withdraw",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )

            self.hijack_queue = Queue(
                "db-hijack-update-{}".format(uuid()),
                exchange=self.hijack_hashing,
                routing_key="1",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )

            self.hijack_ongoing_request_queue = Queue(
                "db-hijack-request-ongoing",
                exchange=self.hijack_exchange,
                routing_key="ongoing-request",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.hijack_outdate_queue = Queue(
                "db-hijack-outdate",
                exchange=self.hijack_exchange,
                routing_key="outdate",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.hijack_resolved_queue = Queue(
                "db-hijack-resolve",
                exchange=self.hijack_exchange,
                routing_key="resolved",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            self.hijack_ignored_queue = Queue(
                "db-hijack-ignored",
                exchange=self.hijack_exchange,
                routing_key="ignored",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            self.handled_queue = Queue(
                "db-handled-update",
                exchange=self.handled_exchange,
                routing_key="update",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.config_queue = Queue(
                "db-config-notify",
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            self.db_clock_queue = Queue(
                "db-clock-{}".format(uuid()),
                exchange=self.db_clock_exchange,
                routing_key="pulse",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 3},
            )
            self.mitigate_queue = Queue(
                "db-mitigation-start",
                exchange=self.mitigation_exchange,
                routing_key="mit-start",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            self.hijack_comment_queue = Queue(
                "db-hijack-comment",
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.hijack_seen_queue = Queue(
                "db-hijack-seen",
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            self.hijack_multiple_action_queue = Queue(
                "db-hijack-multiple-action",
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            self.config_request_rpc()

            log.info("started")

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.update_queue],
                    on_message=self.handle_bgp_update,
                    prefetch_count=100,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_queue],
                    on_message=self.handle_hijack_update,
                    prefetch_count=100,
                    no_ack=True,
                    accept=["pickle"],
                ),
                Consumer(
                    queues=[self.withdraw_queue],
                    on_message=self.handle_withdraw_update,
                    prefetch_count=100,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.db_clock_queue],
                    on_message=self._scheduler_instruction,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.handled_queue],
                    on_message=self.handle_handled_bgp_update,
                    prefetch_count=100,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_resolved_queue],
                    on_message=self.handle_resolved_hijack,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.mitigate_queue],
                    on_message=self.handle_mitigation_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_ignored_queue],
                    on_message=self.handle_hijack_ignore_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_comment_queue],
                    on_message=self.handle_hijack_comment,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_seen_queue],
                    on_message=self.handle_hijack_seen,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_multiple_action_queue],
                    on_message=self.handle_hijack_multiple_action,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_ongoing_request_queue],
                    on_message=self.handle_hijack_ongoing_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_outdate_queue],
                    on_message=self.handle_hijack_outdate,
                    prefetch_count=1,
                    no_ack=True,
                ),
            ]

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
                routing_key="config-request-queue",
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        "config-request-queue",
                        durable=False,
                        max_priority=4,
                        consumer_arguments={"x-priority": 4},
                    ),
                    callback_queue,
                ],
                priority=4,
            )
            with Consumer(
                self.connection,
                on_message=self.handle_config_request_reply,
                queues=[callback_queue],
                no_ack=True,
            ):
                while not self.rules:
                    self.connection.drain_events()

        def handle_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
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
                except Exception:
                    log.exception("{}".format(msg_))
            # reset timer each time we hit the same BGP update
            self.redis.expire(msg_["key"], 60 * 60)

        def handle_withdraw_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
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
            try:
                raw = message.payload
                self.outdate_hijacks.add((raw["persistent_hijack_key"],))
            except Exception:
                log.exception("{}".format(message))

        def handle_hijack_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            msg_ = message.payload
            try:
                key = msg_["key"]  # persistent hijack key

                if not self.redis.sismember("persistent-keys", key):
                    # fetch BGP updates with deprecated hijack keys and
                    # republish to detection
                    rekey_update_keys = list(msg_["monitor_keys"])
                    rekey_updates = []
                    try:
                        query = (
                            "SELECT key, prefix, origin_as, peer_asn, as_path, service, "
                            "type, communities, timestamp FROM bgp_updates "
                            "WHERE bgp_updates.handled=false AND bgp_updates.key = %s"
                        )

                        with get_ro_cursor(self.ro_conn) as db_cur:
                            psycopg2.extras.execute_batch(
                                db_cur, query, (rekey_update_keys,)
                            )
                            entries = db_cur.fetchall()

                        for entry in entries:
                            rekey_updates.append(
                                {
                                    "key": entry[0],  # key
                                    "prefix": entry[1],  # prefix
                                    "origin_as": entry[2],  # origin_as
                                    "peer_asn": entry[3],  # peer_asn
                                    "path": entry[4],  # as_path
                                    "service": entry[5],  # service
                                    "type": entry[6],  # type
                                    "communities": entry[7],  # communities
                                    "timestamp": entry[8].timestamp(),
                                }
                            )

                        # delete monitor keys from redis so that they can be
                        # reprocessed
                        for key in rekey_update_keys:
                            self.redis.delete(key)

                        # send to detection
                        self.producer.publish(
                            rekey_updates,
                            exchange=self.update_exchange,
                            routing_key="hijack-rekey",
                            retry=False,
                            priority=1,
                        )
                    except Exception:
                        log.exception("exception")
                    return

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
                    self.insert_hijacks_entries[key]["monitor_keys"] = msg_[
                        "monitor_keys"
                    ]
                    self.insert_hijacks_entries[key]["time_detected"] = msg_[
                        "time_detected"
                    ]
                    self.insert_hijacks_entries[key]["configured_prefix"] = msg_[
                        "configured_prefix"
                    ]
                    self.insert_hijacks_entries[key]["timestamp_of_config"] = msg_[
                        "timestamp_of_config"
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
            except Exception:
                log.exception("{}".format(msg_))

        def handle_handled_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            try:
                key_ = (message.payload,)
                self.handled_bgp_entries.add(key_)
            except Exception:
                log.exception("{}".format(message))

        def build_radix_tree(self):
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                rule_translated_prefix_set = set()
                for i, prefix in enumerate(rule["prefixes"]):
                    this_translated_prefix_list = flatten(translate_rfc2622(prefix))
                    rule_translated_prefix_set.update(set(this_translated_prefix_list))
                rule["prefixes"] = list(rule_translated_prefix_set)
                for prefix in rule["prefixes"]:
                    node = self.prefix_tree.search_exact(prefix)
                    if not node:
                        node = self.prefix_tree.add(prefix)
                        node.data["confs"] = []

                    conf_obj = {
                        "origin_asns": rule["origin_asns"],
                        "neighbors": rule["neighbors"],
                    }
                    node.data["confs"].append(conf_obj)

        def find_best_prefix_match(self, prefix):
            prefix_node = self.prefix_tree.search_best(prefix)
            if prefix_node:
                return prefix_node.prefix
            return None

        def handle_config_notify(self, message):
            log.debug("Message: {}\npayload: {}".format(message, message.payload))
            config = message.payload
            try:
                if config["timestamp"] > self.timestamp:
                    self.timestamp = config["timestamp"]
                    self.rules = config.get("rules", [])
                    self.build_radix_tree()
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

                    config_hash = hashlib.shake_128(pickle.dumps(raw_config)).hexdigest(
                        16
                    )
                    self._save_config(config_hash, config, raw_config, comment)
            except Exception:
                log.exception("{}".format(config))

        def handle_config_request_reply(self, message):
            log.debug("Message: {}\npayload: {}".format(message, message.payload))
            config = message.payload
            try:
                if self.correlation_id == message.properties["correlation_id"]:
                    if config["timestamp"] > self.timestamp:
                        self.timestamp = config["timestamp"]
                        self.rules = config.get("rules", [])
                        self.build_radix_tree()
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
                        config_hash = hashlib.shake_128(
                            pickle.dumps(raw_config)
                        ).hexdigest(16)
                        latest_config_in_db_hash = (
                            self._retrieve_most_recent_config_hash()
                        )
                        if config_hash != latest_config_in_db_hash:
                            self._save_config(config_hash, config, raw_config, comment)
                        else:
                            log.debug("database config is up-to-date")
            except Exception:
                log.exception("{}".format(config))

        def handle_hijack_ongoing_request(self, message):
            timestamp = message.payload

            # need redis to handle future case of multiple db processes
            last_timestamp = self.redis.get("last_handled_timestamp")
            if not last_timestamp or timestamp > float(last_timestamp):
                self.redis.set("last_handled_timestamp", timestamp)
                try:
                    results = []
                    query = (
                        "SELECT DISTINCT ON(h.key) b.key, b.prefix, b.as_path, b.type, h.key, h.hijack_as, h.type "
                        "FROM hijacks AS h LEFT JOIN bgp_updates AS b ON (h.key = ANY(b.hijack_key)) "
                        "WHERE h.active = true AND b.type='A' AND b.handled=true"
                    )

                    with get_ro_cursor(self.ro_conn) as db_cur:
                        db_cur.execute(query)
                        entries = db_cur.fetchall()

                    for entry in entries:
                        results.append(
                            {
                                "key": entry[0],  # key
                                "prefix": entry[1],  # prefix
                                "path": entry[2],  # as_path
                                "type": entry[3],  # type
                                "hij_key": entry[4],
                                "hijack_as": entry[5],
                                "hij_type": entry[6],
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
                            )
                except Exception:
                    log.exception("exception")

        def bootstrap_redis(self):
            try:
                query = (
                    "SELECT time_started, time_last, peers_seen, "
                    "asns_inf, key, prefix, hijack_as, type, time_detected, "
                    "configured_prefix, timestamp_of_config "
                    "FROM hijacks WHERE active = true"
                )

                with get_ro_cursor(self.ro_conn) as db_cur:
                    db_cur.execute(query)
                    entries = db_cur.fetchall()

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
                    }
                    redis_hijack_key = redis_key(entry[5], entry[6], entry[7])
                    redis_pipeline.set(redis_hijack_key, pickle.dumps(result))
                    redis_pipeline.sadd("persistent-keys", entry[4])
                redis_pipeline.execute()

                query = (
                    "SELECT DISTINCT key, timestamp FROM bgp_updates "
                    "WHERE timestamp > NOW() - interval '1 hours'"
                )

                with get_ro_cursor(self.ro_conn) as db_cur:
                    db_cur.execute(query)
                    entries = db_cur.fetchall()

                redis_pipeline = self.redis.pipeline()
                for entry in entries:
                    expire = int(time.time() - entry[1].timestamp())
                    redis_pipeline.set(entry[0], "1", ex=expire)
                redis_pipeline.execute()
            except Exception:
                log.exception("exception")

        def handle_resolved_hijack(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                # if ongoing, force rekeying and delete persistent too
                if self.redis.sismember("persistent-keys", raw["key"]):
                    purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])

                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, resolved=true, seen=true, time_ended=%s WHERE key=%s;",
                        (datetime.datetime.now(), raw["key"]),
                    )

            except Exception:
                log.exception("{}".format(raw))

        def handle_mitigation_request(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        "UPDATE hijacks SET mitigation_started=%s, seen=true, under_mitigation=true WHERE key=%s;",
                        (datetime.datetime.fromtimestamp(raw["time"]), raw["key"]),
                    )
            except Exception:
                log.exception("{}".format(raw))

        def handle_hijack_ignore_request(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                # if ongoing, force rekeying and delete persistent too
                if self.redis.sismember("persistent-keys", raw["key"]):
                    purge_redis_eph_pers_keys(self.redis, redis_hijack_key, raw["key"])
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, seen=false, ignored=true WHERE key=%s;",
                        (raw["key"],),
                    )
            except Exception:
                log.exception("{}".format(raw))

        def handle_hijack_comment(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        "UPDATE hijacks SET comment=%s WHERE key=%s;",
                        (raw["comment"], raw["key"]),
                    )

                self.producer.publish(
                    {"status": "accepted"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
                )
            except Exception:
                self.producer.publish(
                    {"status": "rejected"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
                )
                log.exception("{}".format(raw))

        def handle_hijack_seen(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        "UPDATE hijacks SET seen=%s WHERE key=%s;",
                        (raw["state"], raw["key"]),
                    )

                self.producer.publish(
                    {"status": "accepted"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
                )
            except Exception:
                self.producer.publish(
                    {"status": "rejected"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
                )
                log.exception("{}".format(raw))

        def handle_hijack_multiple_action(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            query = None
            seen_action = False
            ignore_action = False
            resolve_action = False
            try:
                if not raw["keys"]:
                    query = None
                elif raw["action"] == "mark_resolved":
                    query = "UPDATE hijacks SET resolved=true, active=false, dormant=false, under_mitigation=false, seen=true, time_ended=%s WHERE resolved=false AND ignored=false AND key=%s;"
                    resolve_action = True
                elif raw["action"] == "mark_ignored":
                    query = "UPDATE hijacks SET ignored=true, active=false, dormant=false, under_mitigation=false, seen=false WHERE ignored=false AND resolved=false AND key=%s;"
                    ignore_action = True
                elif raw["action"] == "mark_seen":
                    query = "UPDATE hijacks SET seen=true WHERE key=%s;"
                    seen_action = True
                elif raw["action"] == "mark_not_seen":
                    query = "UPDATE hijacks SET seen=false WHERE key=%s;"
                    seen_action = True

            except Exception:
                log.exception("None action: {}".format(raw))
                query = None

            if not query:
                self.producer.publish(
                    {"status": "rejected"},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
                )
            else:
                for hijack_key in raw["keys"]:
                    try:
                        with get_ro_cursor(self.ro_conn) as db_cur:
                            db_cur.execute(
                                "SELECT prefix, hijack_as, type FROM hijacks WHERE key = %s;",
                                (hijack_key,),
                            )
                            entries = db_cur.fetchall()

                        if entries:
                            entry = entries[0]
                            redis_hijack_key = redis_key(
                                entry[0],
                                entry[1],
                                entry[2],  # prefix  # hijack_as  # type
                            )
                            if seen_action:
                                with get_wo_cursor(self.wo_conn) as db_cur:
                                    db_cur.execute(query, (hijack_key,))
                            elif ignore_action:
                                # if ongoing, force rekeying and delete persistent
                                # too
                                if self.redis.sismember("persistent-keys", hijack_key):
                                    purge_redis_eph_pers_keys(
                                        self.redis, redis_hijack_key, hijack_key
                                    )
                                with get_wo_cursor(self.wo_conn) as db_cur:
                                    db_cur.execute(query, (hijack_key,))
                            elif resolve_action:
                                # if ongoing, force rekeying and delete persistent
                                # too
                                if self.redis.sismember("persistent-keys", hijack_key):
                                    purge_redis_eph_pers_keys(
                                        self.redis, redis_hijack_key, hijack_key
                                    )
                                with get_wo_cursor(self.wo_conn) as db_cur:
                                    db_cur.execute(
                                        query, (datetime.datetime.now(), hijack_key)
                                    )
                            else:
                                raise BaseException("unreachable code reached")

                    except Exception:
                        log.exception("{}".format(raw))

            self.producer.publish(
                {"status": "accepted"},
                exchange="",
                routing_key=message.properties["reply_to"],
                correlation_id=message.properties["correlation_id"],
                serializer="json",
                retry=True,
                priority=4,
            )

        def _insert_bgp_updates(self):
            try:
                query = (
                    "INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, "
                    "timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES %s"
                )
                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_values(
                        db_cur, query, self.insert_bgp_entries, page_size=1000
                    )
            except Exception:
                log.exception("exception")
                return -1
            finally:
                num_of_entries = len(self.insert_bgp_entries)
                self.insert_bgp_entries.clear()
            return num_of_entries

        def _handle_bgp_withdrawals(self):
            query = (
                "SELECT DISTINCT ON (hijacks.key) hijacks.peers_seen, hijacks.peers_withdrawn, "
                "hijacks.key, hijacks.hijack_as, hijacks.type, bgp_updates.timestamp, hijacks.time_last "
                "FROM hijacks LEFT JOIN bgp_updates ON (hijacks.key = ANY(bgp_updates.hijack_key)) "
                "WHERE bgp_updates.prefix = %s "
                "AND bgp_updates.type = 'A' "
                "AND bgp_updates.timestamp >= NOW() - INTERVAL '1 WEEK' "
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
                    with get_ro_cursor(self.ro_conn) as db_cur:
                        db_cur.execute(query, (withdrawal[0], withdrawal[1]))
                        entries = db_cur.fetchall()

                    if not entries:
                        update_normal_withdrawals.add((withdrawal[3],))
                        continue
                    for entry in entries:
                        # entry -> 0: peers_seen, 1: peers_withdrawn, 2:
                        # hij.key, 3: hij.as, 4: hij.type, 5: timestamp
                        # 6: time_last
                        update_hijack_withdrawals.add((entry[2], withdrawal[3]))
                        if entry[5] >= withdrawal[2]:
                            continue
                        # matching withdraw with a hijack
                        if withdrawal[1] not in entry[1] and withdrawal[1] in entry[0]:
                            entry[1].append(withdrawal[1])
                            timestamp = max(withdrawal[2], entry[6])
                            if len(entry[0]) == len(entry[1]):
                                # set hijack as withdrawn and delete from redis
                                redis_hijack_key = redis_key(
                                    withdrawal[0], entry[3], entry[4]
                                )
                                purge_redis_eph_pers_keys(
                                    self.redis, redis_hijack_key, entry[2]
                                )
                                with get_wo_cursor(self.wo_conn) as db_cur:
                                    db_cur.execute(
                                        "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, resolved=false, withdrawn=true, time_ended=%s, "
                                        "peers_withdrawn=%s, time_last=%s WHERE key=%s;",
                                        (timestamp, entry[1], timestamp, entry[2]),
                                    )

                                log.debug("withdrawn hijack {}".format(entry))
                            else:
                                # add withdrawal to hijack
                                with get_wo_cursor(self.wo_conn) as db_cur:
                                    db_cur.execute(
                                        "UPDATE hijacks SET peers_withdrawn=%s, time_last=%s, dormant=false WHERE key=%s;",
                                        (entry[1], timestamp, entry[2]),
                                    )

                                log.debug("updating hijack {}".format(entry))
                except Exception:
                    log.exception("exception")

            try:
                query = (
                    "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[data.v1]) "
                    "FROM (VALUES %s) AS data (v1, v2) WHERE bgp_updates.key=data.v2"
                )
                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_values(
                        db_cur, query, list(update_hijack_withdrawals), page_size=1000
                    )

                query = "UPDATE bgp_updates SET handled=true FROM (VALUES %s) AS data (key) WHERE bgp_updates.key=data.key"
                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_values(
                        db_cur, query, list(update_normal_withdrawals), page_size=1000
                    )
            except Exception:
                log.exception("exception")

            num_of_entries = len(self.handle_bgp_withdrawals)
            self.handle_bgp_withdrawals.clear()
            return num_of_entries

        def _update_bgp_updates(self):
            num_of_updates = 0
            update_bgp_entries = set()
            # Update the BGP entries using the hijack messages
            for hijack_key in self.insert_hijacks_entries:
                for bgp_entry_to_update in self.insert_hijacks_entries[hijack_key][
                    "monitor_keys"
                ]:
                    num_of_updates += 1
                    update_bgp_entries.add((hijack_key, bgp_entry_to_update))
                    # exclude handle bgp updates that point to same hijack as
                    # this
                    self.handled_bgp_entries.discard(bgp_entry_to_update)

            if update_bgp_entries:
                try:
                    query = (
                        "UPDATE hijacks SET peers_withdrawn=array_remove(peers_withdrawn, removed.peer_asn) FROM "
                        "(SELECT witann.key, witann.peer_asn FROM "
                        "(SELECT hij.key, wit.peer_asn, wit.timestamp AS wit_time, ann.timestamp AS ann_time FROM "
                        "((VALUES %s) AS data (v1, v2) LEFT JOIN hijacks AS hij ON (data.v1=hij.key) "
                        "LEFT JOIN bgp_updates AS ann ON (data.v2=ann.key) "
                        "LEFT JOIN bgp_updates AS wit ON (hij.key=ANY(wit.hijack_key))) WHERE "
                        "ann.timestamp >= NOW() - INTERVAL '1 WEEK'  AND wit.timestamp >= NOW() - INTERVAL '1 WEEK' AND "
                        "ann.type='A' AND wit.prefix=ann.prefix AND wit.peer_asn=ann.peer_asn AND wit.type='W' "
                        "ORDER BY wit_time DESC LIMIT 1) AS witann WHERE witann.wit_time < witann.ann_time) "
                        "AS removed WHERE hijacks.key=removed.key"
                    )
                    with get_wo_cursor(self.wo_conn) as db_cur:
                        psycopg2.extras.execute_values(
                            db_cur, query, list(update_bgp_entries), page_size=1000
                        )
                    query = "UPDATE bgp_updates SET handled=true, hijack_key=array_distinct(hijack_key || array[data.v1]) FROM (VALUES %s) AS data (v1, v2) WHERE bgp_updates.key=data.v2"
                    with get_wo_cursor(self.wo_conn) as db_cur:
                        psycopg2.extras.execute_values(
                            db_cur, query, list(update_bgp_entries), page_size=1000
                        )
                except Exception:
                    log.exception("exception")
                    return -1

            num_of_updates += len(update_bgp_entries)
            update_bgp_entries.clear()

            # Update the BGP entries using the handled messages
            if self.handled_bgp_entries:
                try:
                    query = "UPDATE bgp_updates SET handled=true FROM (VALUES %s) AS data (key) WHERE bgp_updates.key=data.key"
                    with get_wo_cursor(self.wo_conn) as db_cur:
                        psycopg2.extras.execute_values(
                            db_cur, query, self.handled_bgp_entries, page_size=1000
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
                    "active, resolved, ignored, withdrawn, dormant, configured_prefix, timestamp_of_config, comment, peers_seen, peers_withdrawn, asns_inf) "
                    "VALUES %s ON CONFLICT(key, time_detected) DO UPDATE SET num_peers_seen=excluded.num_peers_seen, num_asns_inf=excluded.num_asns_inf "
                    ", time_started=excluded.time_started, time_last=excluded.time_last, peers_seen=excluded.peers_seen, asns_inf=excluded.asns_inf, dormant=false"
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
                    )
                    values.append(entry)

                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_values(
                        db_cur, query, values, page_size=1000
                    )
            except Exception:
                log.exception("exception")
                return -1

            num_of_entries = len(self.insert_hijacks_entries)
            self.insert_hijacks_entries.clear()
            return num_of_entries

        # def _retrieve_unhandled(self, amount):
        #     results = []
        #     query = (
        #         "SELECT key, prefix, origin_as, peer_asn, as_path, service, "
        #         "type, communities, timestamp FROM bgp_updates WHERE "
        #         "handled = false ORDER BY timestamp DESC LIMIT(%s)"
        #     )
        #     with get_ro_cursor(self.ro_conn) as db_cur:
        #         db_cur.execute(query, (amount,))
        #         entries = db_cur.fetchall()
        #
        #     for entry in entries:
        #         results.append(
        #             {
        #                 "key": entry[0],  # key
        #                 "prefix": entry[1],  # prefix
        #                 "origin_as": entry[2],  # origin_as
        #                 "peer_asn": entry[3],  # peer_asn
        #                 "path": entry[4],  # as_path
        #                 "service": entry[5],  # service
        #                 "type": entry[6],  # type
        #                 "communities": entry[7],  # communities
        #                 "timestamp": entry[8].timestamp(),
        #             }
        #         )
        #     if results:
        #         self.producer.publish(
        #             results,
        #             exchange=self.update_exchange,
        #             routing_key="unhandled",
        #             retry=False,
        #             priority=2,
        #         )

        def _handle_hijack_outdate(self):
            if not self.outdate_hijacks:
                return
            try:
                query = "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, outdated=true FROM (VALUES %s) AS data (key) WHERE hijacks.key=data.key;"
                with get_wo_cursor(self.wo_conn) as db_cur:
                    psycopg2.extras.execute_values(
                        db_cur, query, list(self.outdate_hijacks), page_size=1000
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
                with get_wo_cursor(self.wo_conn) as db_cur:
                    db_cur.execute(
                        query,
                        (config_hash, raw_config, datetime.datetime.now(), comment),
                    )
            except Exception:
                log.exception("failed to save config in db")

        def _retrieve_most_recent_config_hash(self):
            try:
                with get_ro_cursor(self.ro_conn) as db_cur:
                    db_cur.execute(
                        "SELECT key from configs ORDER BY time_modified DESC LIMIT 1"
                    )
                    hash_ = db_cur.fetchone()

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
