import os
import time

from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import uuid
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
            self.signal_loading_ack = False
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
            msg = {"module": "clock", "loading": status}
            self.correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            with Producer(self.connection) as producer:
                producer.publish(
                    msg,
                    exchange="",
                    routing_key="state-module-loading-queue",
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    retry=True,
                    declare=[
                        Queue(
                            "state-module-loading-queue",
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
                on_message=self.handle_signal_loading_ack,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while not self.signal_loading_ack:
                    self.connection.drain_events()
                self.signal_loading_ack = False

        def handle_signal_loading_ack(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                self.signal_loading_ack = True

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
