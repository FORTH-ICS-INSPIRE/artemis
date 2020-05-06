import difflib
import signal
import time

import ujson as json
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from kombu import Connection
from kombu import Consumer
from kombu import Producer
from kombu import Queue
from kombu import serialization
from kombu import uuid
from utils import get_logger
from utils import GRAPHQL_URI
from utils import GUI_ENABLED
from utils import HASURA_GRAPHQL_ACCESS_KEY
from utils import PROCESS_STATES_LOADING_MUTATION
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
            self.correlation_id = None
            self.signal_loading(True)
            self.response = None
            self.path = "{}/{}".format(d, fn)
            with open(self.path, "r") as f:
                self.content = f.readlines()
            self.signal_loading(False)

        def signal_loading(self, status=False):
            if GUI_ENABLED != "true":
                return
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

                query = gql(PROCESS_STATES_LOADING_MUTATION)

                params = {"name": "observer%", "loading": status}

                client.execute(query, variable_values=params)

            except Exception:
                log.exception("exception")

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
