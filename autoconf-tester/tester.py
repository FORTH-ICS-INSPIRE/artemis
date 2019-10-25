import json
import os
import time

from kombu import Connection
from kombu import Consumer
from kombu import Producer
from kombu import Queue
from kombu import uuid

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)

BACKEND_SUPERVISOR_HOST = os.getenv("BACKEND_SUPERVISOR_HOST", "localhost")
BACKEND_SUPERVISOR_PORT = os.getenv("BACKEND_SUPERVISOR_PORT", 9001)
BACKEND_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
    BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT
)

TESTING_SEQUENCE = [
    "announcement_origin",
    "announcement_origin_with_neighbors",
    "withdrawal",
]


class AutoconfTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.autoconf_rpc_goahead = False
        self.proceed_to_next_test = True

    def handle_autoconf_update_goahead_reply(self, message):
        self.autoconf_rpc_goahead = True

    def send(self, msg):
        with Connection(RABBITMQ_URI) as connection:
            correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            with Producer(connection) as producer:
                print("[+] Sending message '{}'".format(msg))
                producer.publish(
                    msg,
                    exchange="",
                    routing_key="conf-autoconf-update-queue",
                    reply_to=callback_queue.name,
                    correlation_id=correlation_id,
                    retry=True,
                    declare=[
                        Queue(
                            "conf-autoconf-update-queue",
                            durable=False,
                            max_priority=4,
                            consumer_arguments={"x-priority": 4},
                        ),
                        callback_queue,
                    ],
                    priority=4,
                    serializer="json",
                )
                print("[+] Sent message '{}'".format(msg))
            print("[+] Waiting for autoconf RPC to conclude".format(msg))
            self.autoconf_rpc_goahead = False
            with Consumer(
                connection,
                on_message=self.handle_autoconf_update_goahead_reply,
                queues=[callback_queue],
                no_ack=True,
            ):
                while not self.autoconf_rpc_goahead:
                    connection.drain_events()
            print("[+] Autoconf RPC concluded".format(msg))


if __name__ == "__main__":
    print("[+] Starting")
    autoconf_tester = AutoconfTester()

    for i, test in enumerate(TESTING_SEQUENCE):
        print("[+] Commencing test {}: '{}'".format(i + 1, test))
        with open("testfiles/{}.json".format(test), "r") as f:
            message_conf = json.load(f)
            message = message_conf["send"]
            message["timestamp"] = autoconf_tester.time_now + 1
            autoconf_tester.send(message)
            while not autoconf_tester.proceed_to_next_test:
                time.sleep(1)

    # TODO handle conf change check!

    print("[+] Exiting")
