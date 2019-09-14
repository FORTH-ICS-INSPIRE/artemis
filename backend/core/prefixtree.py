import signal
from typing import Dict
from typing import List
from typing import NoReturn

import radix
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from utils import flatten
from utils import get_logger
from utils import RABBITMQ_URI
from utils import translate_asn_range
from utils import translate_rfc2622


log = get_logger()


class PrefixTree:
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

            # EXCHANGES
            self.config_exchange = Exchange(
                "config",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

            # QUEUES
            self.config_queue = Queue(
                "detection-config-notify-{}".format(uuid()),
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=3,
                consumer_arguments={"x-priority": 3},
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
                )
            ]

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
                self.init_prefix_tree()

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
                    self.init_prefix_tree()

        def init_prefix_tree(self) -> NoReturn:
            """
            Updates rules everytime it receives a new configuration.
            """
            self.prefix_tree = radix.Radix()
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
                        "policies": set(rule["policies"]),
                        "community_annotations": rule["community_annotations"],
                    }
                    for prefix in rule["prefixes"]:
                        for translated_prefix in translate_rfc2622(prefix):
                            node = self.prefix_tree.search_exact(translated_prefix)
                            if not node:
                                node = self.prefix_tree.add(translated_prefix)
                                node.data["confs"] = []
                            node.data["confs"].append(conf_obj)
                except Exception:
                    log.exception("Exception")

            def handle_search_exact_rpc(self, message: Dict):
                """
                Callback function for the search exact request RPC.
                """
                log.debug("message: {}\npayload: {}".format(message, message.payload))
                if self.correlation_id == message.properties["correlation_id"]:
                    # raw = message.payload
                    pass

            def handle_search_best_rpc(self, message: Dict):
                """
                Callback function for the search exact request RPC.
                """
                log.debug("message: {}\npayload: {}".format(message, message.payload))
                if self.correlation_id == message.properties["correlation_id"]:
                    # raw = message.payload
                    pass

            def handle_search_worst_rpc(self, message: Dict):
                """
                Callback function for the search exact request RPC.
                """
                log.debug("message: {}\npayload: {}".format(message, message.payload))
                if self.correlation_id == message.properties["correlation_id"]:
                    # raw = message.payload
                    pass


def run():
    service = PrefixTree()
    service.run()


if __name__ == "__main__":
    run()
