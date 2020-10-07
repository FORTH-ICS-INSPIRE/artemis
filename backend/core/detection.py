import ipaddress
import logging
import os
import re
import signal
import time
from datetime import datetime
from typing import Callable
from typing import Dict
from typing import List
from typing import NoReturn
from typing import Tuple

import pytricia
import redis
import ujson as json
from kombu import Connection
from kombu import Consumer
from kombu import Queue
from kombu import serialization
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from utils import exception_handler
from utils import flatten
from utils import get_hash
from utils import get_ip_version
from utils import get_logger
from utils import get_rpki_val_result
from utils import hijack_log_field_formatter
from utils import key_generator
from utils import ping_redis
from utils import purge_redis_eph_pers_keys
from utils import RABBITMQ_URI
from utils import REDIS_HOST
from utils import redis_key
from utils import REDIS_PORT
from utils import RPKI_VALIDATOR_ENABLED
from utils import RPKI_VALIDATOR_HOST
from utils import RPKI_VALIDATOR_PORT
from utils import signal_loading
from utils import TEST_ENV
from utils import translate_asn_range
from utils import translate_rfc2622
from utils.rabbitmq_util import create_exchange
from utils.rabbitmq_util import create_queue

HIJACK_DIM_COMBINATIONS = [
    ["S", "0", "-", "-"],
    ["S", "0", "-", "L"],
    ["S", "1", "-", "-"],
    ["S", "1", "-", "L"],
    ["S", "P", "-", "-"],
    ["S", "-", "-", "-"],
    ["S", "-", "-", "L"],
    ["E", "0", "-", "-"],
    ["E", "0", "-", "L"],
    ["E", "1", "-", "-"],
    ["E", "1", "-", "L"],
    ["E", "P", "-", "-"],
    ["E", "-", "-", "L"],
    ["Q", "0", "-", "-"],
    ["Q", "0", "-", "L"],
]

log = get_logger()
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

# additional serializer for pg-amqp messages
serialization.register(
    "txtjson", json.dumps, json.loads, content_type="text", content_encoding="utf-8"
)


class Detection:
    """
    Detection Service.
    """

    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self) -> NoReturn:
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
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
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):
        """
        RabbitMQ Consumer/Producer for this Service.
        """

        def __init__(self, connection: Connection) -> NoReturn:
            self.module_name = "detection"
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.mon_num = 1
            self.correlation_id = None

            # EXCHANGES
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
            self.config_exchange = create_exchange("config", connection)
            self.pg_amq_bridge = create_exchange("amq.direct", connection)

            # QUEUES
            self.update_queue = create_queue(
                self.module_name,
                exchange=self.pg_amq_bridge,
                routing_key="update-insert",
                priority=1,
            )
            self.hijack_ongoing_queue = create_queue(
                self.module_name,
                exchange=self.hijack_exchange,
                routing_key="ongoing",
                priority=1,
            )
            self.config_queue = create_queue(
                self.module_name,
                exchange=self.config_exchange,
                routing_key="notify",
                priority=3,
                random=True,
            )

            signal_loading(self.module_name, True)

            setattr(self, "publish_hijack_fun", self.publish_hijack_result_production)
            if TEST_ENV == "true":
                setattr(self, "publish_hijack_fun", self.publish_hijack_result_test)

            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            ping_redis(self.redis)

            self.rtrmanager = None
            if RPKI_VALIDATOR_ENABLED == "true":
                from rtrlib import RTRManager

                while True:
                    try:
                        self.rtrmanager = RTRManager(
                            RPKI_VALIDATOR_HOST, RPKI_VALIDATOR_PORT
                        )
                        self.rtrmanager.start()
                        log.info(
                            "Connected to RPKI VALIDATOR '{}:{}'".format(
                                RPKI_VALIDATOR_HOST, RPKI_VALIDATOR_PORT
                            )
                        )
                        break
                    except Exception:
                        log.info(
                            "Could not connect to RPKI VALIDATOR '{}:{}'".format(
                                RPKI_VALIDATOR_HOST, RPKI_VALIDATOR_PORT
                            )
                        )
                        log.info("Retrying RTR connection in 30 seconds...")
                        time.sleep(30)

            self.config_request_rpc()
            log.info("started")
            signal_loading(self.module_name, False)

        def get_consumers(
            self, Consumer: Consumer, channel: Connection
        ) -> List[Consumer]:
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
                    accept=["ujson", "txtjson"],
                ),
                Consumer(
                    queues=[self.hijack_ongoing_queue],
                    on_message=self.handle_ongoing_hijacks,
                    prefetch_count=10,
                    accept=["ujson"],
                ),
            ]

        def on_consume_ready(self, connection, channel, consumers, **kwargs):
            self.producer.publish(
                self.timestamp,
                exchange=self.hijack_exchange,
                routing_key="ongoing-request",
                priority=1,
                serializer="ujson",
            )

        def handle_config_notify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Notify messages that come
            from the configuration service.
            Upon arrival this service updates its running configuration.
            """
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            signal_loading(self.module_name, True)
            try:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.init_detection()
                    # Request ongoing hijacks from DB
                    self.producer.publish(
                        self.timestamp,
                        exchange=self.hijack_exchange,
                        routing_key="ongoing-request",
                        priority=1,
                        serializer="ujson",
                    )
            except Exception:
                log.exception("Exception")
            finally:
                signal_loading(self.module_name, False)

        def config_request_rpc(self) -> NoReturn:
            """
            Initial RPC of this service to request the configuration.
            The RPC is blocked until the configuration service replies back.
            """
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
            log.debug("{}".format(self.rules))

        def handle_config_request_reply(self, message: Dict):
            """
            Callback function for the config request RPC.
            Updates running configuration upon receiving a new configuration.
            """
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.init_detection()

        def init_detection(self) -> NoReturn:
            """
            Updates rules everytime it receives a new configuration.
            """
            log.info("Initiating detection...")

            log.info("Starting building detection prefix tree...")
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
                        "prepend_seq": rule.get("prepend_seq", []),
                        "policies": set(rule["policies"]),
                        "community_annotations": rule["community_annotations"],
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
                "{} prefixes integrated in detection prefix tree in total".format(
                    raw_prefix_count
                )
            )
            log.info("Finished building detection prefix tree.")

            log.info("Detection initiated, configured and running.")

        def handle_ongoing_hijacks(self, message: Dict) -> NoReturn:
            """
            Handles ongoing hijacks from the database.
            """
            log.debug("{} ongoing hijack events".format(len(message.payload)))
            message.ack()
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_bgp_update(self, message: Dict) -> NoReturn:
            """
            Callback function that runs the main logic of
            detecting hijacks for every bgp update.
            """
            # log.debug('{}'.format(message))
            if isinstance(message, dict):
                monitor_event = message
            else:
                message.ack()
                monitor_event = message.payload
                monitor_event["path"] = monitor_event["as_path"]
                monitor_event["timestamp"] = datetime(
                    *map(int, re.findall(r"\d+", monitor_event["timestamp"]))
                ).timestamp()

            raw = monitor_event.copy()

            # mark the initial redis hijack key since it may change upon
            # outdated checks
            if "hij_key" in monitor_event:
                monitor_event["initial_redis_hijack_key"] = redis_key(
                    monitor_event["prefix"],
                    monitor_event["hijack_as"],
                    monitor_event["hij_type"],
                )

            is_hijack = False

            if monitor_event["type"] == "A":
                # save the original path as-is to preserve patterns (if needed)
                monitor_event["orig_path"] = monitor_event["path"][::]
                monitor_event["path"] = Detection.Worker.__clean_as_path(
                    monitor_event["path"]
                )

                ip_version = get_ip_version(monitor_event["prefix"])
                if monitor_event["prefix"] in self.prefix_tree[ip_version]:
                    prefix_node = self.prefix_tree[ip_version][monitor_event["prefix"]]
                    monitor_event["matched_prefix"] = prefix_node["prefix"]

                    final_hij_dimensions = [
                        "-",
                        "-",
                        "-",
                        "-",
                    ]  # prefix, path, dplane, policy
                    for prefix_node_conf in prefix_node["data"]["confs"]:
                        try:
                            path_hijacker = -1
                            pol_hijacker = -1
                            hij_dimensions = [
                                "-",
                                "-",
                                "-",
                                "-",
                            ]  # prefix, path, dplane, policy
                            hij_dimension_index = 0
                            for func_dim in self.__hijack_dimension_checker_gen():
                                if hij_dimension_index == 0:
                                    # prefix dimension
                                    for func_pref in func_dim():
                                        hij_dimensions[hij_dimension_index] = func_pref(
                                            monitor_event, prefix_node, prefix_node_conf
                                        )
                                        if hij_dimensions[hij_dimension_index] != "-":
                                            break
                                elif hij_dimension_index == 1:
                                    # path type dimension
                                    for func_path in func_dim(
                                        len(monitor_event["path"])
                                    ):
                                        (
                                            path_hijacker,
                                            hij_dimensions[hij_dimension_index],
                                        ) = func_path(
                                            monitor_event, prefix_node, prefix_node_conf
                                        )
                                        if hij_dimensions[hij_dimension_index] != "-":
                                            break
                                elif hij_dimension_index == 2:
                                    # data plane dimension
                                    for func_dplane in func_dim():
                                        hij_dimensions[
                                            hij_dimension_index
                                        ] = func_dplane(
                                            monitor_event, prefix_node, prefix_node_conf
                                        )
                                        if hij_dimensions[hij_dimension_index] != "-":
                                            break
                                elif hij_dimension_index == 3:
                                    # policy dimension
                                    for func_pol in func_dim(
                                        len(monitor_event["path"])
                                    ):
                                        (
                                            pol_hijacker,
                                            hij_dimensions[hij_dimension_index],
                                        ) = func_pol(
                                            monitor_event, prefix_node, prefix_node_conf
                                        )
                                        if hij_dimensions[hij_dimension_index] != "-":
                                            break
                                hij_dimension_index += 1
                            # check if dimension combination in hijack combinations for this rule,
                            # but do not commit hijack yet (record the last possible hijack issue)
                            if hij_dimensions in HIJACK_DIM_COMBINATIONS:
                                final_hij_dimensions = hij_dimensions[::]
                                is_hijack = True
                                # show pol hijacker only if the path hijacker is uncertain
                                hijacker = path_hijacker
                                if path_hijacker == -1 and pol_hijacker != -1:
                                    hijacker = pol_hijacker
                            # benign rule matching beats hijack detection
                            else:
                                is_hijack = False
                                break
                        except Exception:
                            log.exception("exception")
                    if is_hijack:
                        try:
                            hij_dimensions = final_hij_dimensions
                            self.commit_hijack(monitor_event, hijacker, hij_dimensions)
                        except Exception:
                            log.exception("exception")

                outdated_hijack = None
                if not is_hijack and "hij_key" in monitor_event:
                    try:
                        # outdated hijack, benign from now on
                        redis_hijack_key = redis_key(
                            monitor_event["prefix"],
                            monitor_event["hijack_as"],
                            monitor_event["hij_type"],
                        )
                        outdated_hijack = self.redis.get(redis_hijack_key)
                        purge_redis_eph_pers_keys(
                            self.redis, redis_hijack_key, monitor_event["hij_key"]
                        )
                        # mark in DB only if it is the first time this hijack was purged (pre-existent in redis)
                        if outdated_hijack:
                            self.mark_outdated(
                                monitor_event["hij_key"], redis_hijack_key
                            )
                    except Exception:
                        log.exception("exception")
                elif (
                    is_hijack
                    and "hij_key" in monitor_event
                    and monitor_event["initial_redis_hijack_key"]
                    != monitor_event["final_redis_hijack_key"]
                ):
                    try:
                        outdated_hijack = self.redis.get(
                            monitor_event["initial_redis_hijack_key"]
                        )
                        # outdated hijack, but still a hijack; need key change
                        purge_redis_eph_pers_keys(
                            self.redis,
                            monitor_event["initial_redis_hijack_key"],
                            monitor_event["hij_key"],
                        )
                        # mark in DB only if it is the first time this hijack was purged (pre-existsent in redis)
                        if outdated_hijack:
                            self.mark_outdated(
                                monitor_event["hij_key"],
                                monitor_event["initial_redis_hijack_key"],
                            )
                    except Exception:
                        log.exception("exception")
                elif not is_hijack:
                    self.gen_implicit_withdrawal(monitor_event)
                    self.mark_handled(raw)

                if outdated_hijack:
                    try:
                        outdated_hijack = json.loads(outdated_hijack)
                        outdated_hijack["end_tag"] = "outdated"
                        mail_log.info(
                            "{}".format(
                                json.dumps(
                                    hijack_log_field_formatter(outdated_hijack),
                                    indent=4,
                                )
                            ),
                            extra={
                                "community_annotation": outdated_hijack.get(
                                    "community_annotation", "NA"
                                )
                            },
                        )
                        hij_log.info(
                            "{}".format(
                                json.dumps(hijack_log_field_formatter(outdated_hijack))
                            ),
                            extra={
                                "community_annotation": outdated_hijack.get(
                                    "community_annotation", "NA"
                                )
                            },
                        )
                    except Exception:
                        log.exception("exception")

            elif monitor_event["type"] == "W":
                self.producer.publish(
                    {
                        "prefix": monitor_event["prefix"],
                        "peer_asn": monitor_event["peer_asn"],
                        "timestamp": monitor_event["timestamp"],
                        "key": monitor_event["key"],
                    },
                    exchange=self.update_exchange,
                    routing_key="withdraw",
                    priority=0,
                    serializer="ujson",
                )

        @staticmethod
        def __remove_prepending(seq: List[int]) -> Tuple[List[int], bool]:
            """
            Static method to remove prepending ASs from AS path.
            """
            last_add = None
            new_seq = []
            for x in seq:
                if last_add != x:
                    last_add = x
                    new_seq.append(x)

            is_loopy = False
            if len(set(seq)) != len(new_seq):
                is_loopy = True
                # raise Exception('Routing Loop: {}'.format(seq))
            return (new_seq, is_loopy)

        @staticmethod
        def __clean_loops(seq: List[int]) -> List[int]:
            """
            Static method that remove loops from AS path.
            """
            # use inverse direction to clean loops in the path of the traffic
            seq_inv = seq[::-1]
            new_seq_inv = []
            for x in seq_inv:
                if x not in new_seq_inv:
                    new_seq_inv.append(x)
                else:
                    x_index = new_seq_inv.index(x)
                    new_seq_inv = new_seq_inv[: x_index + 1]
            return new_seq_inv[::-1]

        @staticmethod
        def __clean_as_path(path: List[int]) -> List[int]:
            """
            Static wrapper method for loop and prepending removal.
            """
            (clean_as_path, is_loopy) = Detection.Worker.__remove_prepending(path)
            if is_loopy:
                clean_as_path = Detection.Worker.__clean_loops(clean_as_path)
            return clean_as_path

        def __hijack_dimension_checker_gen(self) -> Callable:
            """
            Generator that returns hijack dimension checking functions.
            """
            yield self.__hijack_prefix_checker_gen
            yield self.__hijack_path_checker_gen
            yield self.__hijack_dplane_checker_gen
            yield self.__hijack_pol_checker_gen

        def __hijack_prefix_checker_gen(self) -> Callable:
            """
            Generator that returns prefix dimension detection functions.
            """
            yield self.detect_prefix_squatting_hijack
            yield self.detect_prefix_subprefix_hijack

        def __hijack_path_checker_gen(self, path_len: int) -> Callable:
            """
            Generator that returns path dimension detection functions.
            """
            if path_len > 0:
                yield self.detect_path_type_0_hijack
                if path_len > 1:
                    yield self.detect_path_type_1_hijack
                    yield self.detect_path_type_P_hijack
                    if path_len > 2:
                        yield self.detect_path_type_N_hijack
            yield self.detect_path_type_U_hijack

        def __hijack_dplane_checker_gen(self) -> Callable:
            """
            Generator that returns data plane dimension detection functions.
            """
            yield self.detect_dplane_blackholing_hijack
            yield self.detect_dplane_imposture_hijack
            yield self.detect_dplane_mitm_hijack

        def __hijack_pol_checker_gen(self, path_len: int) -> Callable:
            """
            Generator that returns policy dimension detection functions.
            """
            if path_len > 3:
                yield self.detect_pol_leak_hijack
            yield self.detect_pol_other_hijack

        @exception_handler(log)
        def detect_prefix_squatting_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> str:
            """
            Squatting hijack detection.
            """
            # check if there are origin_asns defined (even wildcards)
            if prefix_node_conf["origin_asns"]:
                return "-"
            return "Q"

        @exception_handler(log)
        def detect_prefix_subprefix_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> str:
            """
            Subprefix or exact prefix hijack detection.
            """
            mon_prefix = ipaddress.ip_network(monitor_event["prefix"])
            if (
                ipaddress.ip_network(prefix_node["prefix"]).prefixlen
                < mon_prefix.prefixlen
            ):
                return "S"
            return "E"

        @exception_handler(log)
        def detect_path_type_0_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            """
            Origin hijack detection.
            """
            origin_asn = monitor_event["path"][-1]
            if origin_asn in prefix_node_conf["origin_asns"] or prefix_node_conf[
                "origin_asns"
            ] == [-1]:
                return (-1, "-")
            return (origin_asn, "0")

        @exception_handler(log)
        def detect_path_type_1_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            """
            Type-1 hijack detection.
            """
            origin_asn = monitor_event["path"][-1]
            first_neighbor_asn = monitor_event["path"][-2]
            # [] or [-1] neighbors means "allow everything"
            if (
                origin_asn in prefix_node_conf["origin_asns"]
                or prefix_node_conf["origin_asns"] == [-1]
            ) and (
                (not prefix_node_conf["neighbors"])
                or prefix_node_conf["neighbors"] == [-1]
                or first_neighbor_asn in prefix_node_conf["neighbors"]
            ):
                return (-1, "-")
            return (first_neighbor_asn, "1")

        @exception_handler(log)
        def detect_path_type_P_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            """
            Type-P hijack detection.
            In case there is a type-P hijack (i.e. no pattern matches
            an incoming BGP update), it returns a tuple with the
            potential hijacker AS plus the hijack type (P).
            The potential hijacker is the first AS that differs in the
            most specific (best matching) pattern, starting from the origin
            AS.
            """
            if "orig_path" not in monitor_event:
                return (-1, "-")
            orig_path = monitor_event["orig_path"]
            pattern_matched = False
            pattern_hijacker = -1
            best_match_length = 0
            if len(prefix_node_conf["prepend_seq"]) > 0:
                for conf_seq in prefix_node_conf["prepend_seq"]:
                    if len(orig_path) >= len(conf_seq) + 1:
                        # isolate the monitor event pattern that
                        # should be matched to the configured pattern
                        # (excluding the origin which is the very first hop
                        # of the incoming AS-path)
                        monitor_event_seq = orig_path[
                            len(orig_path) - len(conf_seq) - 1 : -1
                        ]
                        if monitor_event_seq == conf_seq:
                            # patterns match, break (no hijack of type P)
                            pattern_matched = True
                            break
                        else:
                            # calculate the actual differences in the current pattern;
                            # this creates a list of elements with values 0 on matched
                            # elements and !0 otherwise
                            pattern_diffs = [
                                observed_as - conf_as
                                for observed_as, conf_as in zip(
                                    monitor_event_seq, conf_seq
                                )
                            ]
                            this_best_match_length = 0
                            # after reversing the pattern difference sequence (i.e., start with
                            # origin), find the greatest length of consecutive 0s (i.e., non-differences/matches)
                            for diff in pattern_diffs[::-1]:
                                if diff == 0:
                                    # match found, continue increasing the best match length
                                    this_best_match_length += 1
                                else:
                                    # first difference, break here and register the length
                                    break
                            # update the best matching length for all patterns found till now
                            best_match_length = max(
                                best_match_length, this_best_match_length
                            )
            # no hijack (either pattern matching achieved or no configured pattern provided)
            if len(prefix_node_conf["prepend_seq"]) == 0 or pattern_matched:
                return (-1, "-")
            # the hijacker is the first AS that breaks the most specific (best matching) pattern
            pattern_hijacker = orig_path[len(orig_path) - best_match_length - 2]
            return (pattern_hijacker, "P")

        @exception_handler(log)
        def detect_path_type_N_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            # Placeholder for type-N detection (not supported)
            return (-1, "-")

        @exception_handler(log)
        def detect_path_type_U_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            # Placeholder for type-U detection (not supported)
            return (-1, "-")

        @exception_handler(log)
        def detect_dplane_blackholing_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> str:
            # Placeholder for blackholing detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_dplane_imposture_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> str:
            # Placeholder for imposture detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_dplane_mitm_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> str:
            # Placeholder for mitm detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_pol_leak_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            """
            Route leak hijack detection
            """
            if "no-export" in prefix_node_conf["policies"]:
                return (monitor_event["path"][-2], "L")
            return (-1, "-")

        @exception_handler(log)
        def detect_pol_other_hijack(
            self,
            monitor_event: Dict,
            prefix_node: Dict,
            prefix_node_conf: Dict,
            *args,
            **kwargs
        ) -> Tuple[int, str]:
            # Placeholder for policy violation detection (not supported)
            return (-1, "-")

        def commit_hijack(
            self, monitor_event: Dict, hijacker: int, hij_dimensions: List[str]
        ) -> NoReturn:
            """
            Commit new or update an existing hijack to the database.
            It uses redis server to store ongoing hijacks information
            to not stress the db.
            """
            hij_type = "|".join(hij_dimensions)
            redis_hijack_key = redis_key(monitor_event["prefix"], hijacker, hij_type)

            if "hij_key" in monitor_event:
                monitor_event["final_redis_hijack_key"] = redis_hijack_key

            hijack_value = {
                "prefix": monitor_event["prefix"],
                "hijack_as": hijacker,
                "type": hij_type,
                "time_started": monitor_event["timestamp"],
                "time_last": monitor_event["timestamp"],
                "peers_seen": {monitor_event["peer_asn"]},
                "monitor_keys": {monitor_event["key"]},
                "configured_prefix": monitor_event["matched_prefix"],
                "timestamp_of_config": self.timestamp,
                "end_tag": None,
                "outdated_parent": None,
                "rpki_status": "NA",
            }

            if (
                RPKI_VALIDATOR_ENABLED == "true"
                and self.rtrmanager
                and monitor_event["path"]
            ):
                try:
                    asn = monitor_event["path"][-1]
                    if "/" in monitor_event["prefix"]:
                        network, netmask = monitor_event["prefix"].split("/")
                    # /32 or /128
                    else:
                        ip_version = get_ip_version(monitor_event["prefix"])
                        network = monitor_event["prefix"]
                        netmask = 32
                        if ip_version == "v6":
                            netmask = 128
                    redis_rpki_asn_prefix_key = "rpki_as{}_p{}".format(
                        asn, monitor_event["prefix"]
                    )
                    redis_rpki_status = self.redis.get(redis_rpki_asn_prefix_key)
                    if not redis_rpki_status:
                        rpki_status = get_rpki_val_result(
                            self.rtrmanager, asn, network, int(netmask)
                        )
                    else:
                        rpki_status = redis_rpki_status.decode()
                    hijack_value["rpki_status"] = rpki_status
                    # the default refresh interval for the RPKI RTR manager is 3600 seconds
                    self.redis.set(redis_rpki_asn_prefix_key, rpki_status, ex=3600)

                except Exception:
                    log.exception("exception")

            if (
                "hij_key" in monitor_event
                and monitor_event["initial_redis_hijack_key"]
                != monitor_event["final_redis_hijack_key"]
            ):
                hijack_value["outdated_parent"] = monitor_event["hij_key"]

            # identify the number of infected ases
            hijack_value["asns_inf"] = set()
            if hij_dimensions[1] in {"0", "1"}:
                hijack_value["asns_inf"] = set(
                    monitor_event["path"][: -(int(hij_dimensions[1]) + 1)]
                )
            elif hij_dimensions[3] == "L":
                hijack_value["asns_inf"] = set(monitor_event["path"][:-2])
            # assume the worst-case scenario of a type-2 hijack
            elif len(monitor_event["path"]) > 2:
                hijack_value["asns_inf"] = set(monitor_event["path"][:-3])

            # make the following operation atomic using blpop (blocking)
            # first, make sure that the semaphore is initialized
            if self.redis.getset("{}token_active".format(redis_hijack_key), 1) != b"1":
                redis_pipeline = self.redis.pipeline()
                redis_pipeline.lpush("{}token".format(redis_hijack_key), "token")
                # lock, by extracting the token (other processes that access
                # it at the same time will be blocked)
                # attention: it is important that this command is batched in the
                # pipeline since the db may async delete
                # the token
                redis_pipeline.blpop("{}token".format(redis_hijack_key))
                redis_pipeline.execute()
            else:
                # lock, by extracting the token (other processes that access it
                # at the same time will be blocked)
                token = self.redis.blpop("{}token".format(redis_hijack_key), timeout=60)
                # if timeout after 60 seconds, return without hijack alert
                # since this means that sth has been purged in the meanwhile (e.g., due to outdated hijack
                # in another instance; a detector cannot be stuck for a whole minute in a single hijack BGP update)
                if not token:
                    log.info(
                        "Monitor event {} encountered redis token timeout and will be cleared as benign for hijack {}".format(
                            str(monitor_event), redis_hijack_key
                        )
                    )
                    return

            # proceed now that we have clearance
            redis_pipeline = self.redis.pipeline()
            try:
                result = self.redis.get(redis_hijack_key)
                if result:
                    result = json.loads(result)
                    result["time_started"] = min(
                        result["time_started"], hijack_value["time_started"]
                    )
                    result["time_last"] = max(
                        result["time_last"], hijack_value["time_last"]
                    )
                    result["peers_seen"] = set(result["peers_seen"])
                    result["peers_seen"].update(hijack_value["peers_seen"])

                    result["asns_inf"] = set(result["asns_inf"])
                    result["asns_inf"].update(hijack_value["asns_inf"])

                    # no update since db already knows!
                    result["monitor_keys"] = hijack_value["monitor_keys"]
                    self.comm_annotate_hijack(monitor_event, result)
                    result["outdated_parent"] = hijack_value["outdated_parent"]

                    result["bgpupdate_keys"] = set(result["bgpupdate_keys"])
                    result["bgpupdate_keys"].add(monitor_event["key"])

                    result["rpki_status"] = hijack_value["rpki_status"]
                else:
                    hijack_value["time_detected"] = time.time()
                    hijack_value["key"] = get_hash(
                        [
                            monitor_event["prefix"],
                            hijacker,
                            hij_type,
                            "{0:.6f}".format(hijack_value["time_detected"]),
                        ]
                    )
                    hijack_value["bgpupdate_keys"] = {monitor_event["key"]}
                    redis_pipeline.sadd("persistent-keys", hijack_value["key"])
                    result = hijack_value
                    self.comm_annotate_hijack(monitor_event, result)
                    mail_log.info(
                        "{}".format(
                            json.dumps(hijack_log_field_formatter(result), indent=4)
                        ),
                        extra={
                            "community_annotation": result.get(
                                "community_annotation", "NA"
                            )
                        },
                    )
                redis_pipeline.set(redis_hijack_key, json.dumps(result))

                # store the origin, neighbor combination for this hijack BGP update
                origin = None
                neighbor = None
                if monitor_event["path"]:
                    origin = monitor_event["path"][-1]
                if len(monitor_event["path"]) > 1:
                    neighbor = monitor_event["path"][-2]
                redis_pipeline.sadd(
                    "hij_orig_neighb_{}".format(redis_hijack_key),
                    "{}_{}".format(origin, neighbor),
                )

                # store the prefix and peer ASN for this hijack BGP update
                redis_pipeline.sadd(
                    "prefix_{}_peer_{}_hijacks".format(
                        monitor_event["prefix"], monitor_event["peer_asn"]
                    ),
                    redis_hijack_key,
                )
                redis_pipeline.sadd(
                    "hijack_{}_prefixes_peers".format(redis_hijack_key),
                    "{}_{}".format(monitor_event["prefix"], monitor_event["peer_asn"]),
                )
            except Exception:
                log.exception("exception")
            finally:
                # execute whatever has been accumulated in redis till now
                redis_pipeline.execute()

                # publish hijack
                self.publish_hijack_fun(result, redis_hijack_key)

                hij_log.info(
                    "{}".format(json.dumps(hijack_log_field_formatter(result))),
                    extra={
                        "community_annotation": result.get("community_annotation", "NA")
                    },
                )

                # unlock, by pushing back the token (at most one other process
                # waiting will be unlocked)
                redis_pipeline = self.redis.pipeline()
                redis_pipeline.set("{}token_active".format(redis_hijack_key), 1)
                redis_pipeline.lpush("{}token".format(redis_hijack_key), "token")
                redis_pipeline.execute()

        def mark_handled(self, monitor_event: Dict) -> NoReturn:
            """
            Marks a bgp update as handled on the database.
            """
            # log.debug('{}'.format(monitor_event['key']))
            self.producer.publish(
                monitor_event["key"],
                exchange=self.handled_exchange,
                routing_key="update",
                priority=1,
                serializer="ujson",
            )

        def mark_outdated(self, hij_key: str, redis_hij_key: str) -> NoReturn:
            """
            Marks a hijack as outdated on the database.
            """
            # log.debug('{}'.format(hij_key))
            msg = {"persistent_hijack_key": hij_key, "redis_hijack_key": redis_hij_key}
            self.producer.publish(
                msg,
                exchange=self.hijack_exchange,
                routing_key="outdate",
                priority=1,
                serializer="ujson",
            )

        def publish_hijack_result_production(self, result, redis_hijack_key):
            self.producer.publish(
                result,
                exchange=self.hijack_hashing,
                routing_key=redis_hijack_key,
                priority=0,
                serializer="ujson",
            )

        def publish_hijack_result_test(self, result, redis_hijack_key):
            self.producer.publish(
                result,
                exchange=self.hijack_exchange,
                routing_key="update",
                priority=0,
                serializer="ujson",
            )

            self.producer.publish(
                result,
                exchange=self.hijack_hashing,
                routing_key=redis_hijack_key,
                priority=0,
                serializer="ujson",
            )

        def gen_implicit_withdrawal(self, monitor_event: Dict) -> NoReturn:
            """
            Checks if a benign BGP update should trigger an implicit withdrawal
            """
            # log.debug('{}'.format(monitor_event['key']))
            prefix = monitor_event["prefix"]
            super_prefix = ipaddress.ip_network(prefix).supernet()
            peer_asn = monitor_event["peer_asn"]
            # if the the update's prefix matched exactly or is directly more specific than an originally hijacked prefix
            if self.redis.exists(
                "prefix_{}_peer_{}_hijacks".format(prefix, peer_asn)
            ) or self.redis.exists(
                "prefix_{}_peer_{}_hijacks".format(super_prefix, peer_asn)
            ):
                # generate implicit withdrawal
                withdraw_msg = {
                    "service": "implicit-withdrawal",
                    "type": "W",
                    "prefix": prefix,
                    "path": [],
                    "orig_path": {"triggering_bgp_update": monitor_event},
                    "communities": [],
                    "timestamp": monitor_event["timestamp"] + 1,
                    "peer_asn": peer_asn,
                }
                if not self.redis.exists(
                    "prefix_{}_peer_{}_hijacks".format(prefix, peer_asn)
                ) and self.redis.exists(
                    "prefix_{}_peer_{}_hijacks".format(super_prefix, peer_asn)
                ):
                    withdraw_msg["prefix"] = str(super_prefix)
                key_generator(withdraw_msg)
                self.producer.publish(
                    withdraw_msg,
                    exchange=self.update_exchange,
                    routing_key="update",
                    serializer="ujson",
                )

        def comm_annotate_hijack(self, monitor_event: Dict, hijack: Dict) -> NoReturn:
            """
            Annotates a hijack based on community checks (modifies "community_annotation"
            field in-place)
            """
            try:
                if hijack.get("community_annotation", "NA") in [None, "", "NA"]:
                    hijack["community_annotation"] = "NA"
                bgp_update_communities = set()
                for comm_as_value in monitor_event["communities"]:
                    community = "{}:{}".format(comm_as_value[0], comm_as_value[1])
                    bgp_update_communities.add(community)

                ip_version = get_ip_version(monitor_event["prefix"])
                if monitor_event["prefix"] in self.prefix_tree[ip_version]:
                    prefix_node = self.prefix_tree[ip_version][monitor_event["prefix"]]
                    for item in prefix_node["data"]["confs"]:
                        annotations = []
                        for annotation_element in item.get("community_annotations", []):
                            for annotation in annotation_element:
                                annotations.append(annotation)
                        for annotation_element in item.get("community_annotations", []):
                            for annotation in annotation_element:
                                for community_rule in annotation_element[annotation]:
                                    in_communities = set(community_rule.get("in", []))
                                    out_communities = set(community_rule.get("out", []))
                                    if (
                                        in_communities <= bgp_update_communities
                                        and out_communities.isdisjoint(
                                            bgp_update_communities
                                        )
                                    ):
                                        if hijack["community_annotation"] == "NA":
                                            hijack["community_annotation"] = annotation
                                        elif annotations.index(
                                            annotation
                                        ) < annotations.index(
                                            hijack["community_annotation"]
                                        ):
                                            hijack["community_annotation"] = annotation
            except Exception:
                log.exception("exception")


def run():
    service = Detection()
    service.run()


if __name__ == "__main__":
    run()
