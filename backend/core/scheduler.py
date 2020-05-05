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

            self.module_state_exchange = Exchange(
                "module-state",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.module_state_exchange.declare()

            self.signal_loading(True)
            log.info("started")
            self.signal_loading(False)
            self._db_clock_send()

        def signal_loading(self, status=False):
            with Producer(self.connection) as producer:
                msg = {"module": "clock", "loading": status}
                producer.publish(
                    msg,
                    exchange=self.module_state_exchange,
                    routing_key="loading",
                    retry=True,
                    priority=2,
                    serializer="ujson",
                )

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
