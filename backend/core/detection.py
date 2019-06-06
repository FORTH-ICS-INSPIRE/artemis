import ipaddress
import json
import logging
import re
import signal
import time
from datetime import datetime
from typing import Callable
from typing import Dict
from typing import List
from typing import NoReturn
from typing import Tuple

import radix
import redis
import yaml
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from taps.utils import key_generator
from utils import exception_handler
from utils import flatten
from utils import get_hash
from utils import get_logger
from utils import purge_redis_eph_pers_keys
from utils import RABBITMQ_URI
from utils import redis_key
from utils import translate_rfc2622

HIJACK_DIM_COMBINATIONS = [
    ["S", "0", "-", "-"],
    ["S", "0", "-", "L"],
    ["S", "1", "-", "-"],
    ["S", "1", "-", "L"],
    ["S", "-", "-", "-"],
    ["S", "-", "-", "L"],
    ["E", "0", "-", "-"],
    ["E", "0", "-", "L"],
    ["E", "1", "-", "-"],
    ["E", "1", "-", "L"],
    ["E", "-", "-", "L"],
    ["Q", "0", "-", "-"],
    ["Q", "0", "-", "L"],
]

log = get_logger()
hij_log = logging.getLogger("hijack_logger")
mail_log = logging.getLogger("mail_logger")


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
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.mon_num = 1

            self.redis = redis.Redis(host="localhost", port=6379)

            # EXCHANGES
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
                "handled-update",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

            self.config_exchange = Exchange(
                "config",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

            self.pg_amq_bridge = Exchange(
                "amq.direct", type="direct", durable=True, delivery_mode=1
            )

            # QUEUES
            self.update_queue = Queue(
                "detection-update-update",
                exchange=self.pg_amq_bridge,
                routing_key="update-insert",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.update_unhandled_queue = Queue(
                "detection-update-unhandled",
                exchange=self.update_exchange,
                routing_key="unhandled",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            self.hijack_ongoing_queue = Queue(
                "detection-hijack-ongoing",
                exchange=self.hijack_exchange,
                routing_key="ongoing",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            self.config_queue = Queue(
                "detection-config-notify-{}".format(uuid()),
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=3,
                consumer_arguments={"x-priority": 3},
            )
            self.update_rekey_queue = Queue(
                "detection-update-rekey",
                exchange=self.update_exchange,
                routing_key="hijack-rekey",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )

            self.config_request_rpc()
            log.info("started")

        def get_consumers(
            self, Consumer: Consumer, channel: Connection
        ) -> List[Consumer]:
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
                    prefetch_count=1000,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.update_unhandled_queue],
                    on_message=self.handle_unhandled_bgp_updates,
                    prefetch_count=1000,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_ongoing_queue],
                    on_message=self.handle_ongoing_hijacks,
                    prefetch_count=10,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.update_rekey_queue],
                    on_message=self.handle_rekey_update,
                    prefetch_count=10,
                    no_ack=True,
                ),
            ]

        def on_consume_ready(self, connection, channel, consumers, **kwargs):
            self.producer.publish(
                self.timestamp,
                exchange=self.hijack_exchange,
                routing_key="ongoing-request",
                priority=1,
            )

        def handle_config_notify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Notify messages that come
            from the configuration service.
            Upon arrival this service updates its running configuration.
            """
            log.debug("message: {}\npayload: {}".format(message, message.payload))
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
                )

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
            log.debug("{}".format(self.rules))

        def handle_config_request_reply(self, message: Dict):
            """
            Callback function for the config request RPC.
            Updates running configuration upon receiving a new configuration.
            """
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
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                rule_translated_prefix_set = set()
                for prefix in rule["prefixes"]:
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
                        "policies": set(rule["policies"]),
                    }
                    node.data["confs"].append(conf_obj)

        def handle_ongoing_hijacks(self, message: Dict) -> NoReturn:
            """
            Handles ongoing hijacks from the database.
            """
            # log.debug('{} ongoing hijack events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_unhandled_bgp_updates(self, message: Dict) -> NoReturn:
            """
            Handles unhanlded bgp updates from the database in batches of 50.
            """
            # log.debug('{} unhandled events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_rekey_update(self, message: Dict) -> NoReturn:
            """
            Handles BGP updates, needing hijack rekeying from the database.
            """
            # log.debug('{} rekeying events'.format(len(message.payload)))
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
                monitor_event = json.loads(message.payload)
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
                monitor_event["path"] = Detection.Worker.__clean_as_path(
                    monitor_event["path"]
                )
                prefix_node = self.prefix_tree.search_best(monitor_event["prefix"])

                if prefix_node:
                    monitor_event["matched_prefix"] = prefix_node.prefix

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
                                        monitor_event, prefix_node
                                    )
                                    if hij_dimensions[hij_dimension_index] != "-":
                                        break
                            elif hij_dimension_index == 1:
                                # path type dimension
                                for func_path in func_dim(len(monitor_event["path"])):
                                    (
                                        path_hijacker,
                                        hij_dimensions[hij_dimension_index],
                                    ) = func_path(monitor_event, prefix_node)
                                    if hij_dimensions[hij_dimension_index] != "-":
                                        break
                            elif hij_dimension_index == 2:
                                # data plane dimension
                                for func_dplane in func_dim():
                                    hij_dimensions[hij_dimension_index] = func_dplane(
                                        monitor_event, prefix_node
                                    )
                                    if hij_dimensions[hij_dimension_index] != "-":
                                        break
                            elif hij_dimension_index == 3:
                                # policy dimension
                                for func_pol in func_dim(len(monitor_event["path"])):
                                    (
                                        pol_hijacker,
                                        hij_dimensions[hij_dimension_index],
                                    ) = func_pol(monitor_event, prefix_node)
                                    if hij_dimensions[hij_dimension_index] != "-":
                                        break
                            hij_dimension_index += 1
                        # check if dimension combination in hijack combinations
                        # and commit hijack
                        if hij_dimensions in HIJACK_DIM_COMBINATIONS:
                            is_hijack = True
                            # show pol hijacker only if the path hijacker is uncertain
                            hijacker = path_hijacker
                            if path_hijacker == -1 and pol_hijacker != -1:
                                hijacker = pol_hijacker
                            self.commit_hijack(monitor_event, hijacker, hij_dimensions)
                    except Exception:
                        log.exception("exception")

                if (not is_hijack and "hij_key" in monitor_event) or (
                    is_hijack
                    and "hij_key" in monitor_event
                    and monitor_event["initial_redis_hijack_key"]
                    != monitor_event["final_redis_hijack_key"]
                ):
                    redis_hijack_key = redis_key(
                        monitor_event["prefix"],
                        monitor_event["hijack_as"],
                        monitor_event["hij_type"],
                    )
                    purge_redis_eph_pers_keys(
                        self.redis, redis_hijack_key, monitor_event["hij_key"]
                    )
                    self.mark_outdated(monitor_event["hij_key"], redis_hijack_key)
                elif not is_hijack:
                    self.gen_implicit_withdrawal(monitor_event)
                    self.mark_handled(raw)

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
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> str:
            """
            Squatting hijack detection.
            """
            for item in prefix_node.data["confs"]:
                # check if there are origin_asns defined (even wildcards)
                if item["origin_asns"]:
                    return "-"
            return "Q"

        @exception_handler(log)
        def detect_prefix_subprefix_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> str:
            """
            Subprefix or exact prefix hijack detection.
            """
            mon_prefix = ipaddress.ip_network(monitor_event["prefix"])
            if prefix_node.prefixlen < mon_prefix.prefixlen:
                return "S"
            return "E"

        @exception_handler(log)
        def detect_path_type_0_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> Tuple[int, str]:
            """
            Origin hijack detection.
            """
            origin_asn = monitor_event["path"][-1]
            for item in prefix_node.data["confs"]:
                if origin_asn in item["origin_asns"] or item["origin_asns"] == [-1]:
                    return (-1, "-")
            return (origin_asn, "0")

        @exception_handler(log)
        def detect_path_type_1_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> Tuple[int, str]:
            """
            Type-1 hijack detection.
            """
            origin_asn = monitor_event["path"][-1]
            first_neighbor_asn = monitor_event["path"][-2]
            for item in prefix_node.data["confs"]:
                # [] or [-1] neighbors means "allow everything"
                if (
                    origin_asn in item["origin_asns"] or item["origin_asns"] == [-1]
                ) and (
                    (not item["neighbors"])
                    or item["neighbors"] == [-1]
                    or first_neighbor_asn in item["neighbors"]
                ):
                    return (-1, "-")
            return (first_neighbor_asn, "1")

        @exception_handler(log)
        def detect_path_type_N_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> Tuple[int, str]:
            # Placeholder for type-N detection (not supported)
            return (-1, "-")

        @exception_handler(log)
        def detect_path_type_U_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> Tuple[int, str]:
            # Placeholder for type-U detection (not supported)
            return (-1, "-")

        @exception_handler(log)
        def detect_dplane_blackholing_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> str:
            # Placeholder for blackholing detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_dplane_imposture_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> str:
            # Placeholder for imposture detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_dplane_mitm_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> str:
            # Placeholder for mitm detection  (not supported)
            return "-"

        @exception_handler(log)
        def detect_pol_leak_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
        ) -> Tuple[int, str]:
            """
            Route leak hijack detection
            """
            for item in prefix_node.data["confs"]:
                if "no-export" in item["policies"]:
                    return (monitor_event["path"][-2], "L")
            return (-1, "-")

        @exception_handler(log)
        def detect_pol_other_hijack(
            self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs
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
                return

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
            }

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
                self.redis.blpop("{}token".format(redis_hijack_key))

            # proceed now that we have clearance
            redis_pipeline = self.redis.pipeline()
            try:
                result = self.redis.get(redis_hijack_key)
                if result:
                    result = yaml.safe_load(result)
                    result["time_started"] = min(
                        result["time_started"], hijack_value["time_started"]
                    )
                    result["time_last"] = max(
                        result["time_last"], hijack_value["time_last"]
                    )
                    result["peers_seen"].update(hijack_value["peers_seen"])
                    result["asns_inf"].update(hijack_value["asns_inf"])
                    # no update since db already knows!
                    result["monitor_keys"] = hijack_value["monitor_keys"]
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
                    redis_pipeline.sadd("persistent-keys", hijack_value["key"])
                    result = hijack_value
                    mail_log.info("{}".format(result))
                redis_pipeline.set(redis_hijack_key, yaml.dump(result))

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
                # unlock, by pushing back the token (at most one other process
                # waiting will be unlocked)
                redis_pipeline.set("{}token_active".format(redis_hijack_key), 1)
                redis_pipeline.lpush("{}token".format(redis_hijack_key), "token")
                redis_pipeline.execute()

            self.producer.publish(
                result,
                exchange=self.hijack_exchange,
                routing_key="update",
                serializer="yaml",
                priority=0,
            )

            self.producer.publish(
                result,
                exchange=self.hijack_hashing,
                routing_key=redis_hijack_key,
                serializer="yaml",
                priority=0,
            )
            hij_log.info("{}".format(result))

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
            )

        def mark_outdated(self, hij_key: str, redis_hij_key: str) -> NoReturn:
            """
            Marks a hijack as outdated on the database.
            """
            # log.debug('{}'.format(hij_key))
            msg = {"persistent_hijack_key": hij_key, "redis_hijack_key": redis_hij_key}
            self.producer.publish(
                msg, exchange=self.hijack_exchange, routing_key="outdate", priority=1
            )

        def gen_implicit_withdrawal(self, monitor_event: Dict) -> NoReturn:
            """
            Checks if a benign BGP update should trigger an implicit withdrawal
            """
            # log.debug('{}'.format(monitor_event['key']))
            prefix = monitor_event["prefix"]
            peer_asn = monitor_event["peer_asn"]
            if self.redis.exists("prefix_{}_peer_{}_hijacks".format(prefix, peer_asn)):
                # generate implicit withdrawal
                withdraw_msg = {
                    "service": "implicit-withdrawal",
                    "type": "W",
                    "prefix": prefix,
                    "path": [],
                    "orig_path": {"triggering_bgp_update": monitor_event},
                    "communities": [],
                    "timestamp": monitor_event["timestamp"],
                    "peer_asn": peer_asn,
                }
                key_generator(withdraw_msg)
                self.producer.publish(
                    withdraw_msg,
                    exchange=self.update_exchange,
                    routing_key="update",
                    serializer="json",
                )


def run():
    service = Detection()
    service.run()


if __name__ == "__main__":
    run()
