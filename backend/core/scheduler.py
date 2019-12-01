import os
import time

from kombu import Connection
from kombu import Exchange
from kombu import Producer
from utils import get_logger
from utils import RABBITMQ_URI

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
            self.connection = connection
            # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait = float(os.getenv("BULK_TIMER", 1))

            self.db_clock_exchange = Exchange(
                "db-clock",
                type="direct",
                channel=connection,
                durable=False,
                delivery_mode=1,
            )
            self.db_clock_exchange.declare()
            log.info("started")
            self._db_clock_send()

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
