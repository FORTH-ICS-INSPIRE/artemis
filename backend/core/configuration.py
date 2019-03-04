import copy
import json
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
            self.hijack_ignored_rule_queue = Queue(
                "conf-hijack-ignored",
                exchange=self.hijack_exchange,
                routing_key="ignored-rule",
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
                    queues=[self.hijack_ignored_rule_queue],
                    on_message=self.handle_hijack_ignore_rule_request,
                    prefetch_count=1,
                    no_ack=True,
                ),
            ]

        def handle_config_modify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Modify messages that parses and checks if new configuration is correct.
            Replies back to the sender if the configuration is accepted or rejected and notifies all Subscribers if new configuration is used.
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
            Handles all config requests from other Services by replying back with the current configuration.
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

        def handle_hijack_ignore_rule_request(self, message):
            """
            {
                    "key": ...,
                    "prefix": ...,
                    "type": ..._,
                    "hijack_as": ...,
            }
            """
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                redis_hijack_key = redis_key(
                    raw["prefix"], raw["hijack_as"], raw["type"]
                )
                # TODO: make rule dict!!!
            except Exception:
                log.exception("{}".format(raw))

        def parse(
            self, raw: Union[Text, TextIO, StringIO], yaml: Optional[bool] = False
        ) -> Dict:
            """
            Parser for the configuration file or string. The format can either be a File, StringIO or String
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
            Checks if all sections and fields are defined correctly in the parsed configuration.
            Raises custom exceptions in case a field or section is misdefined.
            """
            for section in data:
                if section not in self.sections:
                    raise ArtemisError("invalid-section", section)

            data["prefixes"] = {k: flatten(v) for k, v in data["prefixes"].items()}
            for prefix_group in data["prefixes"]:
                full_translated_prefix_set = set()
                for prefix in data["prefixes"][prefix_group]:
                    this_translated_prefix_list = flatten(translate_rfc2622(prefix))
                    full_translated_prefix_set.update(set(this_translated_prefix_list))
                data["prefixes"][prefix_group] = list(full_translated_prefix_set)
            for prefix_group, prefixes in data["prefixes"].items():
                for prefix in prefixes:
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
                rule_translated_prefix_set = set()
                for i, prefix in enumerate(rule["prefixes"]):
                    this_translated_prefix_list = flatten(translate_rfc2622(prefix))
                    rule_translated_prefix_set.update(set(this_translated_prefix_list))
                rule["prefixes"] = list(rule_translated_prefix_set)
                for prefix in rule["prefixes"]:
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
