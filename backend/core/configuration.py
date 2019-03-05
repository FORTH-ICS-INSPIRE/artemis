import copy
import json
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
from typing import Union

import redis
import ruamel.yaml
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu.mixins import ConsumerProducerMixin
from utils import ArtemisError
from utils import flatten
from utils import get_logger
from utils import RABBITMQ_URI
from utils import redis_key
from utils import translate_rfc2622
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
            }
            self.supported_monitors = {
                "riperis",
                "exabgp",
                "bgpstreamhist",
                "bgpstreamlive",
                "betabmp",
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
            self.available_bgpstreamlive = {"routeviews", "ris"}

            # reads and parses initial configuration file
            with open(self.file, "r") as f:
                raw = f.read()
                self.data, _flag, _error = self.parse(raw, yaml=True)

            # redis
            self.redis = redis.Redis(host="localhost", port=6379)

            # EXCHANGES
            self.config_exchange = Exchange(
                "config",
                type="direct",
                channel=connection,
                durable=False,
                delivery_mode=1,
            )
            self.config_exchange.declare()
            self.hijack_exchange = Exchange(
                "hijack-update",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

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
                "conf-hijack-learn-rule",
                exchange=self.hijack_exchange,
                routing_key="learn-rule",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
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
                    no_ack=True,
                    accept=["yaml"],
                ),
                Consumer(
                    queues=[self.config_request_queue],
                    on_message=self.handle_config_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
                Consumer(
                    queues=[self.hijack_learn_rule_queue],
                    on_message=self.handle_hijack_learn_rule_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
            ]

        def handle_config_modify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Modify messages that parses and checks
            if new configuration is correct.
            Replies back to the sender if the configuration is accepted
            or rejected and notifies all Subscribers if new configuration is used.
            """
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
                        serializer="json",
                        retry=True,
                        priority=2,
                    )
                    # Remove the comment to avoid marking config as different
                    if "comment" in self.data:
                        del self.data["comment"]

                # reply back to the sender with a configuration accepted
                # message.
                self.producer.publish(
                    {"status": "accepted", "config:": self.data},
                    exchange="",
                    routing_key=message.properties["reply_to"],
                    correlation_id=message.properties["correlation_id"],
                    serializer="json",
                    retry=True,
                    priority=4,
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
                    serializer="json",
                    retry=True,
                    priority=4,
                )

        def handle_config_request(self, message: Dict) -> NoReturn:
            """
            Handles all config requests from other Services
            by replying back with the current configuration.
            """
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            self.producer.publish(
                self.data,
                exchange="",
                routing_key=message.properties["reply_to"],
                correlation_id=message.properties["correlation_id"],
                serializer="json",
                retry=True,
                priority=4,
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
                        (origin, neighbor) = list(map(int, element.decode().split("_")))
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
                        raw["key"], raw["prefix"].replace("/", "_").replace(".", "_")
                    )
                }

                # learned rule asns
                rule_asns = {}
                for asn in asns:
                    rule_asns[asn] = "LEARNED_H_{}_AS_{}".format(raw["key"], asn)

                # learned rule(s)
                if re.match(r"^[E|S]\|0.*", raw["type"]):
                    assert len(orig_to_neighb) == 1
                    assert raw["hijack_as"] in orig_to_neighb
                    learned_rule = {
                        "prefixes": [rule_prefix[raw["prefix"]]],
                        "origin_asns": [rule_asns[raw["hijack_as"]]],
                        "neighbors": [
                            rule_asns[asn] for asn in orig_to_neighb[raw["hijack_as"]]
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
                            rule_asns[asn] for asn in neighb_to_origs[raw["hijack_as"]]
                        ],
                        "neighbors": [rule_asns[raw["hijack_as"]]],
                        "mitigation": "manual",
                    }
                    rules.append(learned_rule)
                elif re.match(r"^[E|S]\|-.*", raw["type"]) or re.match(
                    r"^Q\|0.*", raw["type"]
                ):
                    for origin in orig_to_neighb:
                        learned_rule = {
                            "prefixes": [rule_prefix[raw["prefix"]]],
                            "origin_asns": [rule_asns[origin]],
                            "neighbors": [
                                rule_asns[asn] for asn in orig_to_neighb[origin]
                            ],
                            "mitigation": "manual",
                        }
                        rules.append(learned_rule)
            except Exception:
                log.exception("{}".format(raw))

            return (rule_prefix, rule_asns, rules)

        def translate_learn_rule_dicts_to_yaml_file(
            self, rule_prefix, rule_asns, rules
        ):
            """
            Translates the dicts from translate_learn_rule_msg_to_dicts
            function into yaml configuration,
            preserving the order and comments of the current file
            :param rule_prefix: <str>
            :param rule_asns: <list><int>
            :param rules: <list><dict>
            :return: <str>
            """
            extra_yaml_conf_to_show = ruamel.yaml.comments.CommentedMap()
            try:
                with open(self.file, "r") as f:
                    raw = f.read()
                yaml_conf = ruamel.yaml.load(raw, Loader=ruamel.yaml.RoundTripLoader)

                # append prefix
                extra_yaml_conf_to_show[
                    "prefixes"
                ] = ruamel.yaml.comments.CommentedMap()
                for prefix in rule_prefix:
                    prefix_anchor = rule_prefix[prefix]
                    if prefix_anchor not in yaml_conf["prefixes"]:
                        yaml_conf["prefixes"][
                            prefix_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        extra_yaml_conf_to_show["prefixes"][
                            prefix_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        yaml_conf["prefixes"][prefix_anchor].append(prefix)
                        extra_yaml_conf_to_show["prefixes"][prefix_anchor].append(
                            prefix
                        )
                        yaml_conf["prefixes"][prefix_anchor].yaml_set_anchor(
                            prefix_anchor, always_dump=True
                        )
                        extra_yaml_conf_to_show["prefixes"][
                            prefix_anchor
                        ].yaml_set_anchor(prefix_anchor, always_dump=True)
                    else:
                        return "rule already exists"

                # append asns
                extra_yaml_conf_to_show["asns"] = ruamel.yaml.comments.CommentedMap()
                for asn in rule_asns:
                    asn_anchor = rule_asns[asn]
                    if asn_anchor not in yaml_conf["asns"]:
                        yaml_conf["asns"][
                            asn_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        extra_yaml_conf_to_show["asns"][
                            asn_anchor
                        ] = ruamel.yaml.comments.CommentedSeq()
                        yaml_conf["asns"][asn_anchor].append(asn)
                        extra_yaml_conf_to_show["asns"][asn_anchor].append(asn)
                        yaml_conf["asns"][asn_anchor].yaml_set_anchor(
                            asn_anchor, always_dump=True
                        )
                        extra_yaml_conf_to_show["asns"][asn_anchor].yaml_set_anchor(
                            asn_anchor, always_dump=True
                        )
                    else:
                        return "rule already exists"

                # append rules
                extra_yaml_conf_to_show["rules"] = ruamel.yaml.comments.CommentedSeq()
                for rule in rules:
                    rule_map = ruamel.yaml.comments.CommentedMap()

                    # append prefix
                    rule_map["prefixes"] = ruamel.yaml.comments.CommentedSeq()
                    for prefix in rule["prefixes"]:
                        rule_map["prefixes"].append(yaml_conf["prefixes"][prefix])

                    # append origin asns
                    rule_map["origin_asns"] = ruamel.yaml.comments.CommentedSeq()
                    for origin_asn in rule["origin_asns"]:
                        rule_map["origin_asns"].append(yaml_conf["asns"][origin_asn])

                    # append neighbors
                    rule_map["neighbors"] = ruamel.yaml.comments.CommentedSeq()
                    for neighbor in rule["neighbors"]:
                        rule_map["neighbors"].append(yaml_conf["asns"][neighbor])

                    # append mitigation action
                    rule_map["mitigation"] = rule["mitigation"]

                    yaml_conf["rules"].append(rule_map)
                    extra_yaml_conf_to_show["rules"].append(rule_map)

                # generate new configuration
                with open(self.file, "w") as f:
                    ruamel.yaml.dump(yaml_conf, f, Dumper=ruamel.yaml.RoundTripDumper)

            except Exception:
                log.exception("{}-{}-{}".format(rule_prefix, rule_asns, rules))
                return None
            return ruamel.yaml.dump(
                extra_yaml_conf_to_show, Dumper=ruamel.yaml.RoundTripDumper
            )

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
            }
            :return: -
            """
            raw = message.payload
            log.debug("payload: {}".format(raw))
            (rule_prefix, rule_asns, rules) = self.translate_learn_rule_msg_to_dicts(
                raw
            )
            extra_yaml_conf_to_show = self.translate_learn_rule_dicts_to_yaml_file(
                rule_prefix, rule_asns, rules
            )
            log.info(extra_yaml_conf_to_show)

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

            data["prefixes"] = {k: flatten(v) for k, v in data["prefixes"].items()}
            for prefix_group, prefixes in data["prefixes"].items():
                for prefix in prefixes:
                    if translate_rfc2622(prefix, just_match=True):
                        continue
                    try:
                        str2ip(prefix)
                    except Exception:
                        raise ArtemisError("invalid-prefix", prefix)

            for rule in data["rules"]:
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
                for asn in rule["origin_asns"] + rule["neighbors"]:
                    if not isinstance(asn, int):
                        raise ArtemisError("invalid-asn", asn)

            if "monitors" in data:
                for key, info in data["monitors"].items():
                    if key not in self.supported_monitors:
                        raise ArtemisError("invalid-monitor", key)
                    elif key == "riperis":
                        for unavailable in set(info).difference(self.available_ris):
                            log.warning("unavailable monitor {}".format(unavailable))
                    elif key == "bgpstreamlive":
                        if not info or not set(info).issubset(
                            self.available_bgpstreamlive
                        ):
                            raise ArtemisError("invalid-bgpstreamlive-project", info)
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

            data["asns"] = {k: flatten(v) for k, v in data["asns"].items()}
            for name, asns in data["asns"].items():
                for asn in asns:
                    if not isinstance(asn, int):
                        raise ArtemisError("invalid-asn", asn)
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
