import time

from artemis_utils import BULK_TIMER
from artemis_utils import get_logger
from artemis_utils import RABBITMQ_URI
from artemis_utils import signal_loading
from artemis_utils.rabbitmq_util import create_exchange
from kombu import Connection
from kombu import Producer

log = get_logger()


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
            self.module_name = "clock"
            self.clock = 0.0
            self.connection = connection
            # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait_bulk = BULK_TIMER
            self.correlation_id = None

            self.db_clock_exchange = create_exchange(
                "db-clock", connection, declare=True
            )

            signal_loading(self.module_name, True)
            log.info("started")
            signal_loading(self.module_name, False)
            self._db_clock_send()

        def _db_clock_send(self):
            with Producer(self.connection) as producer:
                while True:
                    time.sleep(self.time_to_wait_bulk)
                    self.clock += self.time_to_wait_bulk
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
