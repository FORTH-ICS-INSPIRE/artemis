import os
import time

from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from utils import get_logger
from utils import GRAPHQL_URI
from utils import HASURA_GRAPHQL_ACCESS_KEY
from utils import RABBITMQ_URI

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


class Scheduler:
    def run(self):
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
        except Exception:
            log.exception("exception")
        except KeyboardInterrupt:
            pass
        finally:
            log.info("stopped")

    class Worker:
        def __init__(self, connection):
            self.connection = connection
            # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait = float(os.getenv("BULK_TIMER", 1))
            self.correlation_id = None

            self.db_clock_exchange = Exchange(
                "db-clock",
                type="direct",
                channel=connection,
                durable=False,
                delivery_mode=1,
            )
            self.db_clock_exchange.declare()

            self.signal_loading(True)
            log.info("started")
            self.signal_loading(False)
            self._db_clock_send()

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

                params = {"name": "clock", "loading": status}

                client.execute(query, variable_values=params)

            except Exception:
                log.exception("exception")

        def _db_clock_send(self):
            with Producer(self.connection) as producer:
                while True:
                    time.sleep(self.time_to_wait)
                    producer.publish(
                        {"op": "bulk_operation"},
                        exchange=self.db_clock_exchange,
                        routing_key="pulse",
                        retry=True,
                        priority=3,
                        serializer="ujson",
                    )


def run():
    service = Scheduler()
    service.run()


if __name__ == "__main__":
    run()
