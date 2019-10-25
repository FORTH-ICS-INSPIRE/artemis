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


class AutoconfTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.autoconf_goahead = False

    def handle_autoconf_update_goahead_reply(self, message):
        self.autoconf_goahead = True

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
            with Consumer(
                connection,
                on_message=self.handle_autoconf_update_goahead_reply,
                queues=[callback_queue],
                no_ack=True,
            ):
                while not self.autoconf_goahead:
                    connection.drain_events()


if __name__ == "__main__":
    print("[+] Starting")
    autoconf_tester = AutoconfTester()

    print("[+] Sending announcement with origin only")
    announcement_origin = {
        "key": 1,
        "type": "A",
        "timestamp": autoconf_tester.time_now + 1,
        "path": [1],
        "service": "test-autoconf",
        "communities": [],
        "prefix": "192.168.0.0/16",
        "peer_asn": 1,
    }
    autoconf_tester.send(announcement_origin)
    print("[+] Announcement with origin only sent")

    # TODO handle conf change check!

    print("[+] Sending announcement with origin and neighbors")
    announcement_origin_with_neighbors = {
        "key": 2,
        "type": "A",
        "timestamp": autoconf_tester.time_now + 2,
        "path": [1],
        "service": "test-autoconf",
        "communities": [{"asn": 1, "value": 2}, {"asn": 1, "value": 3}],
        "prefix": "192.168.0.0/16",
        "peer_asn": 1,
    }
    autoconf_tester.send(announcement_origin_with_neighbors)
    print("[+] Announcement with origin and neighbors sent")

    # TODO handle conf change check!

    print("[+] Sending prefix withdrawal")
    withdrawal = {
        "key": 3,
        "type": "W",
        "timestamp": autoconf_tester.time_now + 2,
        "path": [],
        "service": "test-autoconf",
        "communities": [],
        "prefix": "192.168.0.0/16",
        "peer_asn": 1,
    }
    print("[+] Withdrawal sent")

    # TODO handle conf change check!

    print("[+] Exiting")
