import signal
import subprocess
import time

import pytricia
import ujson as json
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from utils import get_ip_version
from utils import get_logger
from utils import GRAPHQL_URI
from utils import HASURA_GRAPHQL_ACCESS_KEY
from utils import RABBITMQ_URI
from utils import translate_rfc2622

log = get_logger()

process_states_loading_mutation = """
    mutation updateProcessStates($name: String, $loading: Boolean) {
        update_view_processes(where: {name: {_eq: $name}}, _set: {loading: $loading}) {
        affected_rows
        returning {
          name
          loading
        }
      }
    }
"""


class Mitigation:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
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
        def __init__(self, connection):
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.correlation_id = None

            # EXCHANGES
            self.mitigation_exchange = Exchange(
                "mitigation",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.mitigation_exchange.declare()
            self.config_exchange = Exchange(
                "config", type="direct", durable=False, delivery_mode=1
            )

            # QUEUES
            self.config_queue = Queue(
                "mitigation-config-notify",
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=3,
                consumer_arguments={"x-priority": 3},
            )
            self.mitigate_queue = Queue(
                "mitigation-mitigate",
                exchange=self.mitigation_exchange,
                routing_key="mitigate",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )

            self.signal_loading(True)
            self.config_request_rpc()
            self.signal_loading(False)

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.mitigate_queue],
                    on_message=self.handle_mitigation_request,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
            ]

        def signal_loading(self, status=False):
            try:

                transport = RequestsHTTPTransport(
                    url=GRAPHQL_URI,
                    use_json=True,
                    headers={
                        "Content-type": "application/json; charset=utf-8",
                        "x-hasura-admin-secret": HASURA_GRAPHQL_ACCESS_KEY,
                    },
                    verify=False,
                )

                client = Client(
                    retries=3, transport=transport, fetch_schema_from_transport=True
                )

                query = gql(process_states_loading_mutation)

                params = {"name": "mitigation", "loading": status}

                client.execute(query, variable_values=params)

            except Exception:
                log.exception("exception")

        def handle_config_notify(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            self.signal_loading(True)
            raw = message.payload
            if raw["timestamp"] > self.timestamp:
                self.timestamp = raw["timestamp"]
                self.rules = raw.get("rules", [])
                self.init_mitigation()
            self.signal_loading(False)

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

        def handle_config_request_reply(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.init_mitigation()

        def init_mitigation(self):
            log.info("Initiating mitigation...")

            log.info("Starting building mitigation prefix tree...")
            self.prefix_tree = {
                "v4": pytricia.PyTricia(32),
                "v6": pytricia.PyTricia(128),
            }
            raw_prefix_count = 0
            for rule in self.rules:
                try:
                    for prefix in rule["prefixes"]:
                        for translated_prefix in translate_rfc2622(prefix):
                            ip_version = get_ip_version(translated_prefix)
                            node = {
                                "prefix": translated_prefix,
                                "data": {"mitigation": rule["mitigation"]},
                            }
                            self.prefix_tree[ip_version].insert(translated_prefix, node)
                            raw_prefix_count += 1
                except Exception:
                    log.exception("Exception")
            log.info(
                "{} prefixes integrated in mitigation prefix tree in total".format(
                    raw_prefix_count
                )
            )
            log.info("Finished building mitigation prefix tree.")

            log.info("Mitigation initiated, configured and running.")

        def handle_mitigation_request(self, message):
            message.ack()
            hijack_event = message.payload
            ip_version = get_ip_version(hijack_event["prefix"])
            if hijack_event["prefix"] in self.prefix_tree[ip_version]:
                prefix_node = self.prefix_tree[ip_version][hijack_event["prefix"]]
                mitigation_action = prefix_node["data"]["mitigation"][0]
                if mitigation_action == "manual":
                    log.info(
                        "starting manual mitigation of hijack {}".format(hijack_event)
                    )
                else:
                    log.info(
                        "starting custom mitigation of hijack {} using '{}' script".format(
                            hijack_event, mitigation_action
                        )
                    )
                    hijack_event_str = json.dumps(hijack_event)
                    subprocess.Popen(
                        [mitigation_action, "-i", hijack_event_str],
                        shell=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                # do something
                mit_started = {"key": hijack_event["key"], "time": time.time()}
                self.producer.publish(
                    mit_started,
                    exchange=self.mitigation_exchange,
                    routing_key="mit-start",
                    priority=2,
                    serializer="ujson",
                )
            else:
                log.warn("no rule for hijack {}".format(hijack_event))


def run():
    service = Mitigation()
    service.run()


if __name__ == "__main__":
    run()
