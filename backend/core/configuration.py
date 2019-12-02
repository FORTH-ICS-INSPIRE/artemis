import copy
import re
import signal
import time
from io import StringIO
from ipaddress import ip_network as str2ip
from typing import Dict
from typing import List
from typing import NoReturn
from typing import Optional
from typing import Text
from typing import TextIO
from typing import Tuple
from typing import Union

import redis
import ruamel.yaml
import ujson as json
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu.mixins import ConsumerProducerMixin
from utils import ArtemisError
from utils import flatten
from utils import get_logger
from utils import ping_redis
from utils import RABBITMQ_URI
from utils import REDIS_HOST
from utils import redis_key
from utils import REDIS_PORT
from utils import translate_as_set
from utils import translate_asn_range
from utils import translate_rfc2622
from utils import update_aliased_list
from yaml import load as yload

log = get_logger()


class Configuration:
    """
    Configuration Service.
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
            self.file = "/etc/artemis/config.yaml"
            self.sections = {"prefixes", "asns", "monitors", "rules"}
            self.supported_fields = {
                "prefixes",
                "policies",
                "origin_asns",
                "neighbors",
                "mitigation",
                "community_annotations",
            }
            self.supported_monitors = {
                "riperis",
                "exabgp",
                "bgpstreamhist",
                "bgpstreamlive",
                "bgpstreamkafka",
            }
            self.available_ris = {
                "rrc01",
                "rrc02",
                "rrc03",
                "rrc04",
                "rrc05",
                "rrc06",
                "rrc07",
                "rrc08",
                "rrc09",
                "rrc10",
                "rrc11",
                "rrc12",
                "rrc13",
                "rrc14",
                "rrc15",
                "rrc16",
                "rrc17",
                "rrc18",
                "rrc19",
                "rrc20",
                "rrc21",
                "rrc22",
                "rrc23",
                "rrc00",
            }
            self.available_bgpstreamlive = {"routeviews", "ris", "caida"}
            self.required_bgpstreamkafka = {"host", "port", "topic"}

            # reads and parses initial configuration file
            with open(self.file, "r") as f:
                raw = f.read()
                self.data, _flag, _error = self.parse(raw, yaml=True)

            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            ping_redis(self.redis)

            # EXCHANGES
            self.config_exchange = Exchange(
                "config",
                type="direct",
                channel=connection,
                durable=False,
                delivery_mode=1,
            )
            self.config_exchange.declare()

            # QUEUES
            self.config_modify_queue = Queue(
                "config-modify-queue",
                durable=False,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.config_request_queue = Queue(
                "config-request-queue",
                durable=False,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.hijack_learn_rule_queue = Queue(
                "conf-hijack-learn-rule-queue",
                durable=False,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.load_as_sets_queue = Queue(
                "conf-load-as-sets-queue",
                durable=False,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            self.autoconf_update_queue = Queue(
                "conf-autoconf-update-queue",
                durable=False,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            log.info("started")

        def get_consumers(
            self, Consumer: Consumer, channel: Connection
        ) -> List[Consumer]:
            return [
                Consumer(
                    queues=[self.config_modify_queue],
                    on_message=self.handle_config_modify,
                    prefetch_count=1,
                    accept=["yaml"],
                ),
                Consumer(
                    queues=[self.config_request_queue],
                    on_message=self.handle_config_request,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.hijack_learn_rule_queue],
                    on_message=self.handle_hijack_learn_rule_request,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.load_as_sets_queue],
                    on_message=self.handle_load_as_sets,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.autoconf_update_queue],
                    on_message=self.handle_autoconf_updates,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
            ]

        def handle_config_modify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Modify messages that parses and checks
            if new configuration is correct.
            Replies back to the sender if the configuration is accepted
            or rejected and notifies all Subscribers if new configuration is used.
            """
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            raw_ = message.payload

            # Case received config from Frontend with comment
            comment = None
            if isinstance(raw_, dict) and "comment" in raw_:
                comment = raw_["comment"]
                del raw_["comment"]
                raw = raw_["config"]
            else:
                raw = raw_

            if "yaml" in message.content_type:
                stream = StringIO("".join(raw))
                data, _flag, _error = self.parse(stream, yaml=True)
            else:
                data, _flag, _error = self.parse(raw)

            # _flag is True or False depending if the new configuration was
            # accepted or not.
            if _flag:
                log.debug("accepted new configuration")
                # compare current with previous data excluding --obviously-- timestamps
                # change to sth better
                prev_data = copy.deepcopy(data)
                del prev_data["timestamp"]
                new_data = copy.deepcopy(self.data)
                del new_data["timestamp"]
                prev_data_str = json.dumps(prev_data, sort_keys=True)
                new_data_str = json.dumps(new_data, sort_keys=True)
                if prev_data_str != new_data_str:
                    self.data = data
                    self._update_local_config_file()
                    if comment:
                        self.data["comment"] = comment

                    self.producer.publish(
                        self.data,
                        exchange=self.config_exchange,
                        routing_key="notify",
                        retry=True,
                        priority=2,
                        serializer="ujson",
                    )
                    # Remove the comment to avoid marking config as different
                    if "comment" in self.data:
                        del self.data["comment"]
                    # after accepting/writing, format new configuration correctly
                    with open(self.file, "r") as f:
                        raw = f.read()
                    yaml_conf = ruamel.yaml.load(
                        raw, Loader=ruamel.yaml.RoundTripLoader, preserve_quotes=True
                    )
                    ruamel.yaml.dump(yaml_conf, Dumper=ruamel.yaml.RoundTripDumper)
                    with open(self.file, "w") as f:
                        ruamel.yaml.dump(
                            yaml_conf, f, Dumper=ruamel.yaml.RoundTripDumper
                        )

                # reply back to the sender with a configuration accepted
                # message.
                self.producer.publish(
                    {"status": "accepted", "config:": self.data},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
            else:
                log.debug("rejected new configuration")
                # replay back to the sender with a configuration rejected and
                # reason message.
                self.producer.publish(
                    {"status": "rejected", "reason": _error},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )

        def handle_config_request(self, message: Dict) -> NoReturn:
            """
            Handles all config requests from other Services
            by replying back with the current configuration.
            """
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            self.producer.publish(
                self.data,
                exchange="",
                routing_key=message.properties["reply_to"],
                correlation_id=message.properties["correlation_id"],
                retry=True,
                priority=4,
                serializer="ujson",
            )

        def translate_learn_rule_msg_to_dicts(self, raw):
            """
            Translates a learn rule message payload (raw)
            into ARTEMIS-compatible dictionaries
            :param raw:
                "key": <str>,
                "prefix": <str>,
                "type": <str>,
                "hijack_as": <int>,
            }
            :return: (<str>rule_prefix, <list><int>rule_asns,
            <list><dict>rules)
            """
            # initialize dictionaries and lists
            rule_prefix = {}
            rule_asns = {}
            rules = []

            try:
                # retrieve (origin, neighbor) combinations from redis
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                hij_orig_neighb_set = "hij_orig_neighb_{}".format(redis_hijack_key)
                orig_to_neighb = {}
                neighb_to_origs = {}
                asns = set()
                if self.redis.exists(hij_orig_neighb_set):
                    for element in self.redis.sscan_iter(hij_orig_neighb_set):
                        (origin_str, neighbor_str) = element.decode().split("_")
                        origin = None
                        if origin_str != "None":
                            origin = int(origin_str)
                        neighbor = None
                        if neighbor_str != "None":
                            neighbor = int(neighbor_str)
                        if origin is not None:
                            asns.add(origin)
                            if origin not in orig_to_neighb:
                                orig_to_neighb[origin] = set()
                            if neighbor is not None:
                                asns.add(neighbor)
                                orig_to_neighb[origin].add(neighbor)
                                if neighbor not in neighb_to_origs:
                                    neighb_to_origs[neighbor] = set()
                                neighb_to_origs[neighbor].add(origin)

                # learned rule prefix
                rule_prefix = {
                    raw["prefix"]: "LEARNED_H_{}_P_{}".format(
                        raw["key"],
                        raw["prefix"]
                        .replace("/", "_")
                        .replace(".", "_")
                        .replace(":", "_"),
                    )
                }

                # learned rule asns
                rule_asns = {}
                for asn in sorted(list(asns)):
                    rule_asns[asn] = "LEARNED_H_{}_AS_{}".format(raw["key"], asn)

                # learned rule(s)
                if re.match(r"^[E|S]\|0.*", raw["type"]):
                    assert len(orig_to_neighb) == 1
                    assert raw["hijack_as"] in orig_to_neighb
                    learned_rule = {
                        "prefixes": [rule_prefix[raw["prefix"]]],
                        "origin_asns": [rule_asns[raw["hijack_as"]]],
                        "neighbors": [
                            rule_asns[asn]
                            for asn in sorted(orig_to_neighb[raw["hijack_as"]])
                        ],
                        "mitigation": "manual",
                    }
                    rules.append(learned_rule)
                elif re.match(r"^[E|S]\|1.*", raw["type"]):
                    assert len(neighb_to_origs) == 1
                    assert raw["hijack_as"] in neighb_to_origs
                    learned_rule = {
                        "prefixes": [rule_prefix[raw["prefix"]]],
                        "origin_asns": [
                            rule_asns[asn]
                            for asn in sorted(neighb_to_origs[raw["hijack_as"]])
                        ],
                        "neighbors": [rule_asns[raw["hijack_as"]]],
                        "mitigation": "manual",
                    }
                    rules.append(learned_rule)
                elif re.match(r"^[E|S]\|-.*", raw["type"]) or re.match(
                    r"^Q\|0.*", raw["type"]
                ):
                    for origin in sorted(orig_to_neighb):
                        learned_rule = {
                            "prefixes": [rule_prefix[raw["prefix"]]],
                            "origin_asns": [rule_asns[origin]],
                            "neighbors": [
                                rule_asns[asn] for asn in sorted(orig_to_neighb[origin])
                            ],
                            "mitigation": "manual",
                        }
                        rules.append(learned_rule)
            except Exception:
                log.exception("{}".format(raw))
                return (None, None, None)

            return (rule_prefix, rule_asns, rules)

        def get_created_prefix_anchors_from_new_rule(self, yaml_conf, rule_prefix):
            created_prefix_anchors = set()
            try:
                for prefix in rule_prefix:
                    prefix_anchor = rule_prefix[prefix]
                    if "prefixes" not in yaml_conf:
                        yaml_conf["prefixes"] = ruamel.yaml.comments.CommentedMap()
                    if prefix_anchor not in yaml_conf["prefixes"]:
                        yaml_conf["prefixes"][
                            prefix_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        yaml_conf["prefixes"][prefix_anchor].append(prefix)
                        created_prefix_anchors.add(prefix_anchor)
                    yaml_conf["prefixes"][prefix_anchor].yaml_set_anchor(
                        prefix_anchor, always_dump=True
                    )
            except Exception:
                log.exception("exception")
                return set()
            return created_prefix_anchors

        def get_created_asn_anchors_from_new_rule(self, yaml_conf, rule_asns):
            created_asn_anchors = set()
            try:
                for asn in sorted(rule_asns):
                    asn_anchor = rule_asns[asn]
                    if "asns" not in yaml_conf:
                        yaml_conf["asns"] = ruamel.yaml.comments.CommentedMap()
                    if asn_anchor not in yaml_conf["asns"]:
                        yaml_conf["asns"][
                            asn_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        yaml_conf["asns"][asn_anchor].append(asn)
                        created_asn_anchors.add(asn_anchor)
                    yaml_conf["asns"][asn_anchor].yaml_set_anchor(
                        asn_anchor, always_dump=True
                    )
            except Exception:
                log.exception("exception")
            return created_asn_anchors

        def get_existing_rules_from_new_rule(
            self, yaml_conf, rule_prefix, rule_asns, rule
        ):
            try:
                # calculate origin asns for the new rule (int format)
                new_rule_origin_asns = set()
                for origin_asn_anchor in rule["origin_asns"]:

                    # translate origin asn anchor into integer for quick retrieval
                    origin_asn = None
                    for asn in rule_asns:
                        if rule_asns[asn] == origin_asn_anchor:
                            origin_asn = asn
                            break
                    if origin_asn:
                        new_rule_origin_asns.add(origin_asn)

                # calculate neighbors for the new rule (int format)
                new_rule_neighbors = set()
                if "neighbors" in rule and rule["neighbors"]:
                    for neighbor_anchor in rule["neighbors"]:

                        # translate neighbor anchor into integer for quick retrieval
                        neighbor = None
                        for asn in rule_asns:
                            if rule_asns[asn] == neighbor_anchor:
                                neighbor = asn
                                break
                        if neighbor:
                            new_rule_neighbors.add(neighbor)

                # check existence of rule (by checking the affected prefixes, origin_asns, and neighbors)
                existing_rules_found = set()
                rule_extension_needed = set()
                if "rules" not in yaml_conf:
                    yaml_conf["rules"] = ruamel.yaml.comments.CommentedSeq()
                for i, existing_rule in enumerate(yaml_conf["rules"]):
                    existing_rule_prefixes = set()
                    for existing_prefix_seq in existing_rule["prefixes"]:
                        if isinstance(existing_prefix_seq, str):
                            existing_rule_prefixes.add(existing_prefix_seq)
                            continue
                        for existing_prefix in existing_prefix_seq:
                            existing_rule_prefixes.add(existing_prefix)
                    if set(rule_prefix.keys()) == existing_rule_prefixes:
                        # same prefixes, proceed to origin asn checking

                        # calculate the origin asns of the existing rule
                        existing_origin_asns = set()
                        if "origin_asns" in existing_rule:
                            for existing_origin_asn_seq in existing_rule["origin_asns"]:
                                if existing_origin_asn_seq:
                                    if isinstance(existing_origin_asn_seq, int):
                                        existing_origin_asns.add(
                                            existing_origin_asn_seq
                                        )
                                        continue
                                    for existing_origin_asn in existing_origin_asn_seq:
                                        if existing_origin_asn != -1:
                                            existing_origin_asns.add(
                                                existing_origin_asn
                                            )
                        if new_rule_origin_asns == existing_origin_asns:
                            # same prefixes, proceed to neighbor checking

                            # calculate the neighbors of the existing rule
                            existing_neighbors = set()
                            if "neighbors" in existing_rule:
                                for existing_neighbor_seq in existing_rule["neighbors"]:
                                    if existing_neighbor_seq:
                                        if isinstance(existing_neighbor_seq, int):
                                            existing_neighbors.add(
                                                existing_neighbor_seq
                                            )
                                            continue
                                        for existing_neighbor in existing_neighbor_seq:
                                            if existing_neighbor != -1:
                                                existing_neighbors.add(
                                                    existing_neighbor
                                                )
                            if new_rule_neighbors == existing_neighbors:
                                # existing rule found, do nothing
                                existing_rules_found.add(i)
                            elif not existing_neighbors:
                                existing_rules_found.add(i)
                                # rule extension needed if wildcarded neighbors
                                rule_extension_needed.add(i)
            except Exception:
                log.exception("exception")
                return (set(), set())
            return (existing_rules_found, rule_extension_needed)

        def translate_learn_rule_dicts_to_yaml_conf(
            self, rule_prefix, rule_asns, rules, withdrawal=False
        ):
            """
            Translates the dicts from translate_learn_rule_msg_to_dicts
            function into yaml configuration,
            preserving the order and comments of the current file
            :param rule_prefix: <str>
            :param rule_asns: <list><int>
            :param rules: <list><dict>
            :param withdrawal: <bool>
            :return: (<dict>, <bool>)
            """

            if (withdrawal and not rule_prefix) or (
                not withdrawal and (not rule_prefix or not rule_asns or not rules)
            ):
                return ("problem with rule installation", False)
            yaml_conf = None
            try:
                with open(self.file, "r") as f:
                    raw = f.read()
                yaml_conf = ruamel.yaml.load(
                    raw, Loader=ruamel.yaml.RoundTripLoader, preserve_quotes=True
                )

                if rule_prefix and withdrawal:
                    rules_to_be_deleted = []
                    for existing_rule in yaml_conf["rules"]:
                        prefix_seqs_to_be_deleted = []
                        for existing_prefix_seq in existing_rule["prefixes"]:
                            if isinstance(existing_prefix_seq, str):
                                for prefix in rule_prefix:
                                    if existing_prefix_seq == prefix:
                                        prefix_seqs_to_be_deleted.append(
                                            existing_prefix_seq
                                        )
                                        break
                                continue
                            for existing_prefix in existing_prefix_seq:
                                for prefix in rule_prefix:
                                    if existing_prefix == prefix:
                                        prefix_seqs_to_be_deleted.append(
                                            existing_prefix_seq
                                        )
                                        break
                        if len(prefix_seqs_to_be_deleted) == len(
                            existing_rule["prefixes"]
                        ):
                            # same prefixes, rule needs to be deleted
                            rules_to_be_deleted.append(existing_rule)
                        elif prefix_seqs_to_be_deleted:
                            # only the rule prefix(es) need to be deleted
                            for prefix_seq in prefix_seqs_to_be_deleted:
                                existing_rule["prefixes"].remove(prefix_seq)
                    for rule in rules_to_be_deleted:
                        yaml_conf["rules"].remove(rule)
                    for prefix_anchor in rule_prefix.values():
                        if prefix_anchor in yaml_conf["prefixes"]:
                            del yaml_conf["prefixes"][prefix_anchor]
                    return (yaml_conf, True)

                # create prefix anchors
                created_prefix_anchors = self.get_created_prefix_anchors_from_new_rule(
                    yaml_conf, rule_prefix
                )

                # create asn anchors
                created_asn_anchors = self.get_created_asn_anchors_from_new_rule(
                    yaml_conf, rule_asns
                )

                # append rules
                for rule in rules:
                    (
                        existing_rules_found,
                        rule_update_needed,
                    ) = self.get_existing_rules_from_new_rule(
                        yaml_conf, rule_prefix, rule_asns, rule
                    )
                    # if no existing rule, make a new one
                    if not existing_rules_found:
                        rule_map = ruamel.yaml.comments.CommentedMap()

                        # append prefix
                        rule_map["prefixes"] = ruamel.yaml.comments.CommentedSeq()
                        for prefix in rule["prefixes"]:
                            rule_map["prefixes"].append(yaml_conf["prefixes"][prefix])

                        # append origin asns
                        rule_map["origin_asns"] = ruamel.yaml.comments.CommentedSeq()
                        for origin_asn_anchor in rule["origin_asns"]:
                            rule_map["origin_asns"].append(
                                yaml_conf["asns"][origin_asn_anchor]
                            )

                        # append neighbors
                        rule_map["neighbors"] = ruamel.yaml.comments.CommentedSeq()
                        if "neighbors" in rule and rule["neighbors"]:
                            for neighbor_anchor in rule["neighbors"]:
                                rule_map["neighbors"].append(
                                    yaml_conf["asns"][neighbor_anchor]
                                )
                        else:
                            del rule_map["neighbors"]

                        # append mitigation action
                        rule_map["mitigation"] = rule["mitigation"]

                        yaml_conf["rules"].append(rule_map)
                    # else delete any created anchors (not needed), as long as no rule update is needed
                    elif not rule_update_needed:
                        for prefix_anchor in created_prefix_anchors:
                            del yaml_conf["prefixes"][prefix_anchor]
                        for asn_anchor in created_asn_anchors:
                            del yaml_conf["asns"][asn_anchor]
                    # rule update needed (neighbors)
                    else:
                        for existing_rule_found in existing_rules_found:
                            rule_map = yaml_conf["rules"][existing_rule_found]
                            if "neighbors" in rule and rule["neighbors"]:
                                if existing_rule_found in rule_update_needed:
                                    rule_map[
                                        "neighbors"
                                    ] = ruamel.yaml.comments.CommentedSeq()
                                    for neighbor_anchor in rule["neighbors"]:
                                        rule_map["neighbors"].append(
                                            yaml_conf["asns"][neighbor_anchor]
                                        )

            except Exception:
                log.exception("{}-{}-{}".format(rule_prefix, rule_asns, rules))
                return (
                    "problem with rule installation; exception during yaml processing",
                    False,
                )
            return (yaml_conf, True)

        def handle_hijack_learn_rule_request(self, message):
            """
            Receives a "learn-rule" message, translates this
            to associated ARTEMIS-compatibe dictionaries,
            and adds the prefix, asns and rule(s) to the configuration
            :param message: {
                "key": <str>,
                "prefix": <str>,
                "type": <str>,
                "hijack_as": <int>,
                "action": <str> show|approve
            }
            :return: -
            """
            message.ack()
            raw = message.payload
            log.debug("payload: {}".format(raw))
            (rule_prefix, rule_asns, rules) = self.translate_learn_rule_msg_to_dicts(
                raw
            )
            (yaml_conf, ok) = self.translate_learn_rule_dicts_to_yaml_conf(
                rule_prefix, rule_asns, rules
            )
            if ok:
                yaml_conf_str = ruamel.yaml.dump(
                    yaml_conf, Dumper=ruamel.yaml.RoundTripDumper
                )
            else:
                yaml_conf_str = yaml_conf

            if raw["action"] == "approve" and ok:
                # store the new configuration to file
                with open(self.file, "w") as f:
                    ruamel.yaml.dump(yaml_conf, f, Dumper=ruamel.yaml.RoundTripDumper)

            if raw["action"] in ["show", "approve"]:
                # reply back to the sender with the extra yaml configuration
                # message.
                self.producer.publish(
                    {"success": ok, "new_yaml_conf": yaml_conf_str},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
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
            (clean_as_path, is_loopy) = Configuration.Worker.__remove_prepending(path)
            if is_loopy:
                clean_as_path = Configuration.Worker.__clean_loops(clean_as_path)
            return clean_as_path

        def translate_bgp_update_to_dicts(self, bgp_update):
            """
            Translates a BGP update message payload
            into ARTEMIS-compatible dictionaries
            :param bgp_update: {
                "prefix": <str>,
                "key": <str>,
                "peer_asn": <int>,
                "path": (<int>)<list>
                "service": <str>,
                "type": <str>,
                "communities": [
                    ...,
                    {
                        "asn": <int>,
                        "value": <int>
                    },
                    ...,
                ]
                "timestamp" : <float>
            }
            :return: (<str>rule_prefix, <list><int>rule_asns,
            <list><dict>rules)
            """
            # initialize dictionaries and lists
            rule_prefix = {}
            rule_asns = {}
            rules = []

            try:
                if bgp_update["type"] == "A":

                    # learned rule prefix
                    rule_prefix = {
                        bgp_update["prefix"]: "AUTOCONF_P_{}".format(
                            bgp_update["prefix"]
                            .replace("/", "_")
                            .replace(".", "_")
                            .replace(":", "_")
                        )
                    }

                    # learned rule asns
                    as_path = Configuration.Worker.__clean_as_path(bgp_update["path"])
                    if len(as_path) > 1:
                        # ignore, since this is not a self-network origination, but sth transit
                        return (None, None, None)
                    origin_asn = None
                    neighbor = None
                    asns = set()
                    if as_path:
                        origin_asn = as_path[-1]
                        asns.add(origin_asn)
                    neighbors = set()
                    if "communities" in bgp_update:
                        for community in bgp_update["communities"]:
                            asn = int(community["asn"])
                            value = int(community["value"])
                            if asn == origin_asn and value != origin_asn:
                                neighbors.add(value)
                    for neighbor in neighbors:
                        asns.add(neighbor)

                    rule_asns = {}
                    for asn in sorted(list(asns)):
                        rule_asns[asn] = "AUTOCONF_AS_{}".format(asn)

                    # learned rule
                    learned_rule = {
                        "prefixes": [rule_prefix[bgp_update["prefix"]]],
                        "origin_asns": [rule_asns[origin_asn]],
                        "mitigation": "manual",
                    }
                    if neighbors:
                        learned_rule["neighbors"] = []
                        for neighbor in neighbors:
                            learned_rule["neighbors"].append(rule_asns[neighbor])
                    rules.append(learned_rule)
                else:
                    # learned rule prefix
                    rule_prefix = {
                        bgp_update["prefix"]: "AUTOCONF_P_{}".format(
                            bgp_update["prefix"]
                            .replace("/", "_")
                            .replace(".", "_")
                            .replace(":", "_")
                        )
                    }

            except Exception:
                log.exception("{}".format(bgp_update))
                return (None, None, None)

            return (rule_prefix, rule_asns, rules)

        def handle_autoconf_updates(self, message):
            """
            Receives a "autoconf-update" message, translates the corresponding
            BGP update into ARTEMIS configuration and rewrites the configuration
            :param message:
            :return:
            """
            message.ack()
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))

            try:
                bgp_update = message.payload
                # if you have seen the exact same update before, do nothing
                if self.redis.get(bgp_update["key"]):
                    self.producer.publish(
                        "",
                        exchange="",
                        routing_key=message.properties["reply_to"],
                        correlation_id=message.properties["correlation_id"],
                        retry=True,
                        priority=4,
                        serializer="ujson",
                    )
                    return

                (rule_prefix, rule_asns, rules) = self.translate_bgp_update_to_dicts(
                    bgp_update
                )
                withdrawal = False
                if bgp_update["type"] == "W":
                    withdrawal = True
                (yaml_conf, ok) = self.translate_learn_rule_dicts_to_yaml_conf(
                    rule_prefix, rule_asns, rules, withdrawal=withdrawal
                )
                if ok:
                    # store the new configuration to file
                    with open(self.file, "w") as f:
                        ruamel.yaml.dump(
                            yaml_conf, f, Dumper=ruamel.yaml.RoundTripDumper
                        )
            except Exception:
                log.exception("exception")
            finally:
                self.producer.publish(
                    "",
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )

        def handle_load_as_sets(self, message):
            """
            Receives a "load-as-sets" message, translates the corresponding
            as anchors into lists, and rewrites the configuration
            :param message:
            :return:
            """
            message.ack()
            with open(self.file, "r") as f:
                raw = f.read()
            yaml_conf = ruamel.yaml.load(
                raw, Loader=ruamel.yaml.RoundTripLoader, preserve_quotes=True
            )
            error = False
            done_as_set_translations = {}
            if "asns" in yaml_conf:
                for name in yaml_conf["asns"]:
                    as_members = []
                    # consult cache
                    if name in done_as_set_translations:
                        as_members = done_as_set_translations[name]
                    # else try to retrieve from API
                    elif translate_as_set(name, just_match=True):
                        ret_dict = translate_as_set(name, just_match=False)
                        if ret_dict["success"] and "as_members" in ret_dict["payload"]:
                            as_members = ret_dict["payload"]["as_members"]
                            done_as_set_translations[name] = as_members
                        else:
                            error = ret_dict["error"]
                            break
                    if as_members:
                        new_as_set_cseq = ruamel.yaml.comments.CommentedSeq()
                        for asn in as_members:
                            new_as_set_cseq.append(asn)
                        new_as_set_cseq.yaml_set_anchor(name)
                        update_aliased_list(
                            yaml_conf, yaml_conf["asns"][name], new_as_set_cseq
                        )

            if error:
                ret_json = {"success": False, "payload": {}, "error": error}
            elif done_as_set_translations:
                ret_json = {
                    "success": True,
                    "payload": {
                        "message": "All ({}) AS-SET translations done".format(
                            len(done_as_set_translations)
                        )
                    },
                    "error": False,
                }
            else:
                ret_json = {
                    "success": True,
                    "payload": {"message": "No AS-SET translations were needed"},
                    "error": False,
                }

            self.producer.publish(
                ret_json,
                exchange="",
                routing_key=message.properties["reply_to"],
                correlation_id=message.properties["correlation_id"],
                retry=True,
                priority=4,
                serializer="ujson",
            )
            # as-sets were resolved, update configuration
            if (not error) and done_as_set_translations:
                with open(self.file, "w") as f:
                    ruamel.yaml.dump(yaml_conf, f, Dumper=ruamel.yaml.RoundTripDumper)

        def parse(
            self, raw: Union[Text, TextIO, StringIO], yaml: Optional[bool] = False
        ) -> Dict:
            """
            Parser for the configuration file or string.
            The format can either be a File, StringIO or String
            """
            try:
                if yaml:
                    data = yload(raw)
                else:
                    data = raw
                data = self.check(data)
                data["timestamp"] = time.time()
                # if raw is string we save it as-is else we get the value.
                if isinstance(raw, str):
                    data["raw_config"] = raw
                else:
                    data["raw_config"] = raw.getvalue()
                return data, True, None
            except Exception as e:
                log.exception("exception")
                return {"timestamp": time.time()}, False, str(e)

        @staticmethod
        def __check_prefixes(_prefixes):
            for prefix_group, prefixes in _prefixes.items():
                for prefix in prefixes:
                    if translate_rfc2622(prefix, just_match=True):
                        continue
                    try:
                        str2ip(prefix)
                    except Exception:
                        raise ArtemisError("invalid-prefix", prefix)

        def __check_rules(self, _rules):
            for rule in _rules:
                for field in rule:
                    if field not in self.supported_fields:
                        log.warning(
                            "unsupported field found {} in {}".format(field, rule)
                        )
                rule["prefixes"] = flatten(rule["prefixes"])
                for prefix in rule["prefixes"]:
                    if translate_rfc2622(prefix, just_match=True):
                        continue
                    try:
                        str2ip(prefix)
                    except Exception:
                        raise ArtemisError("invalid-prefix", prefix)
                rule["origin_asns"] = flatten(rule.get("origin_asns", []))
                if rule["origin_asns"] == ["*"]:
                    rule["origin_asns"] = [-1]
                rule["neighbors"] = flatten(rule.get("neighbors", []))
                if rule["neighbors"] == ["*"]:
                    rule["neighbors"] = [-1]
                rule["mitigation"] = flatten(rule.get("mitigation", "manual"))
                rule["policies"] = flatten(rule.get("policies", []))
                rule["community_annotations"] = rule.get("community_annotations", [])
                if not isinstance(rule["community_annotations"], list):
                    raise ArtemisError("invalid-outer-list-comm-annotations", "")
                seen_community_annotations = set()
                for annotation_entry_outer in rule["community_annotations"]:
                    if not isinstance(annotation_entry_outer, dict):
                        raise ArtemisError("invalid-dict-comm-annotations", "")
                    for annotation in annotation_entry_outer:
                        if annotation in seen_community_annotations:
                            raise ArtemisError(
                                "duplicate-community-annotation", annotation
                            )
                        seen_community_annotations.add(annotation)
                        if not isinstance(annotation_entry_outer[annotation], list):
                            raise ArtemisError(
                                "invalid-inner-list-comm-annotations", annotation
                            )
                        for annotation_entry_inner in annotation_entry_outer[
                            annotation
                        ]:

                            for key in annotation_entry_inner:
                                if key not in ["in", "out"]:
                                    raise ArtemisError(
                                        "invalid-community-annotation-key", key
                                    )
                            in_communities = flatten(
                                annotation_entry_inner.get("in", [])
                            )
                            for community in in_communities:
                                if not re.match(r"\d+\:\d+", community):
                                    raise ArtemisError(
                                        "invalid-bgp-community", community
                                    )
                            out_communities = flatten(
                                annotation_entry_inner.get("out", [])
                            )
                            for community in out_communities:
                                if not re.match(r"\d+\:\d+", community):
                                    raise ArtemisError(
                                        "invalid-bgp-community", community
                                    )

                for asn in rule["origin_asns"] + rule["neighbors"]:
                    if translate_asn_range(asn, just_match=True):
                        continue
                    if not isinstance(asn, int):
                        raise ArtemisError("invalid-asn", asn)

        def __check_monitors(self, _monitors):
            for key, info in _monitors.items():
                if key not in self.supported_monitors:
                    raise ArtemisError("invalid-monitor", key)
                elif key == "riperis":
                    for unavailable in set(info).difference(self.available_ris):
                        log.warning("unavailable monitor {}".format(unavailable))
                elif key == "bgpstreamlive":
                    if not info or not set(info).issubset(self.available_bgpstreamlive):
                        raise ArtemisError("invalid-bgpstreamlive-project", info)
                elif key == "bgpstreamkafka":
                    if not set(info.keys()).issubset(self.required_bgpstreamkafka):
                        raise ArtemisError(
                            "invalid-bgpstreamkakfa-configuration", list(info.keys())
                        )
                elif key == "exabgp":
                    for entry in info:
                        if "ip" not in entry and "port" not in entry:
                            raise ArtemisError("invalid-exabgp-info", entry)
                        if entry["ip"] != "exabgp":
                            try:
                                str2ip(entry["ip"])
                            except Exception:
                                raise ArtemisError("invalid-exabgp-ip", entry["ip"])
                        if not isinstance(entry["port"], int):
                            raise ArtemisError("invalid-exabgp-port", entry["port"])
                        if "autoconf" in entry:
                            if entry["autoconf"] == "true":
                                entry["autoconf"] = True
                            elif entry["autoconf"] == "false":
                                del entry["autoconf"]
                            else:
                                raise ArtemisError(
                                    "invalid-exabgp-autoconf-flag", entry["autoconf"]
                                )
                elif key == "bgpstreamhist":
                    if "dir" in info and "autoconf" in info:
                        if info["autoconf"] == "true":
                            info["autoconf"] = True
                        elif info["autoconf"] == "false":
                            del info["autoconf"]
                        else:
                            raise ArtemisError(
                                "invalid-bgpostreamhist-autoconf-flag", info["autoconf"]
                            )

        @staticmethod
        def __check_asns(_asns):
            for name, asns in _asns.items():
                for asn in asns:
                    if translate_asn_range(asn, just_match=True):
                        continue
                    if not isinstance(asn, int):
                        raise ArtemisError("invalid-asn", asn)

        def check(self, data: Text) -> Dict:
            """
            Checks if all sections and fields are defined correctly
            in the parsed configuration.
            Raises custom exceptions in case a field or section
            is misdefined.
            """
            for section in data:
                if section not in self.sections:
                    raise ArtemisError("invalid-section", section)

            data["prefixes"] = {
                k: flatten(v) for k, v in data.get("prefixes", {}).items()
            }
            data["asns"] = {k: flatten(v) for k, v in data.get("asns", {}).items()}
            data["monitors"] = data.get("monitors", {})
            data["rules"] = data.get("rules", [])

            Configuration.Worker.__check_prefixes(data["prefixes"])
            self.__check_rules(data["rules"])
            self.__check_monitors(data["monitors"])
            Configuration.Worker.__check_asns(data["asns"])

            return data

        def _update_local_config_file(self) -> NoReturn:
            """
            Writes to the local configuration file the new running configuration.
            """
            with open(self.file, "w") as f:
                f.write(self.data["raw_config"])


def run():
    service = Configuration()
    service.run()


if __name__ == "__main__":
    run()
