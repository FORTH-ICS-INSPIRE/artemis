import difflib
import signal
import time

import ujson as json
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import serialization
from kombu import uuid
from utils import get_logger
from utils import RABBITMQ_URI
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchObserver


log = get_logger()

serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)


class Observer:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
        observer = WatchObserver()

        dirname = "/etc/artemis"
        filename = "config.yaml"

        try:
            with Connection(RABBITMQ_URI) as connection:
                event_handler = self.Handler(dirname, filename, connection)
                observer.schedule(event_handler, dirname, recursive=False)
                observer.start()
                log.info("started")
                self.should_stop = False
                while not self.should_stop:
                    time.sleep(5)
        except Exception:
            log.exception("exception")
        finally:
            observer.stop()
            observer.join()
            log.info("stopped")

    def exit(self, signum, frame):
        self.should_stop = True

    class Handler(FileSystemEventHandler):
        def __init__(self, d, fn, connection):
            super().__init__()
            self.connection = connection
            self.module_state_exchange = Exchange(
                "module-state",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            self.module_state_exchange.declare()
            self.signal_loading("start")
            self.response = None
            self.correlation_id = None
            self.path = "{}/{}".format(d, fn)
            with open(self.path, "r") as f:
                self.content = f.readlines()
            self.signal_loading("end")

        def signal_loading(self, status="end"):
            with Producer(self.connection) as producer:
                msg = {"module": "observer", "loading": status}
                producer.publish(
                    msg,
                    exchange=self.module_state_exchange,
                    routing_key="loading",
                    retry=True,
                    priority=2,
                    serializer="ujson",
                )

        def on_response(self, message):
            message.ack()
            if message.properties["correlation_id"] == self.correlation_id:
                self.response = message.payload

        def on_modified(self, event):
            if event.is_directory:
                return None

            if event.src_path == self.path:
                with open(self.path, "r") as f:
                    content = f.readlines()
                # Taken any action here when a file is modified.
                changes = "".join(difflib.unified_diff(self.content, content))
                if changes:
                    self.response = None
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
                            content,
                            exchange="",
                            routing_key="config-modify-queue",
                            serializer="yaml",
                            retry=True,
                            declare=[callback_queue],
                            reply_to=callback_queue.name,
                            correlation_id=self.correlation_id,
                            priority=4,
                        )
                    with Consumer(
                        self.connection,
                        on_message=self.on_response,
                        queues=[callback_queue],
                        accept=["ujson"],
                    ):
                        while self.response is None:
                            self.connection.drain_events()

                    if self.response["status"] == "accepted":
                        text = "new configuration accepted:\n{}".format(changes)
                        log.info(text)
                        self.content = content
                    else:
                        log.error("invalid configuration:\n{}".format(content))
                    self.response = None


def run():
    service = Observer()
    service.run()


if __name__ == "__main__":
    run()
