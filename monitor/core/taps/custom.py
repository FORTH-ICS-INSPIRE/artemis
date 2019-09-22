import threading

from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import uuid
from utils import get_logger
from utils import RABBITMQ_URI

log = get_logger()

recv_cnt = 0
send_cnt = 0


def run():
    def sender(k):
        global send_cnt
        send_cnt = 0
        msg_ = {
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [8, 3, 2, 1, ord(k)],
            "prefix": "10.0.0.0/24",
            "peer_asn": 8,
        }
        with Connection(RABBITMQ_URI) as connection:
            exchange = Exchange(
                "bgp-update", channel=connection, type="direct", durable=False
            )
            exchange.declare()
            with Producer(connection) as producer:
                for x in range(1, 256):
                    for y in range(1, 256):
                        for z in range(1, 256):
                            msg_["timestamp"] = x * 1000000 + y * 1000 + z
                            msg_["key"] = "{}-{}-{}-{}".format(k, x, y, z)
                            msg_["prefix"] = "{}.{}.{}.0/24".format(x, y, z)
                            producer.publish(
                                msg_,
                                exchange=exchange,
                                routing_key="update",
                                serializer="json",
                            )
                            send_cnt += 1
                            print("Total sent {} from {}".format(send_cnt, k))

    def receiver():
        def on_response():
            global recv_cnt
            recv_cnt += 1
            print("Total received {}".format(recv_cnt))

        with Connection(RABBITMQ_URI) as connection:
            hijack_exchange = Exchange(
                "hijack-update",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )
            hijack_exchange.declare()
            hijack_queue = Queue(
                "db-hijack-update-{}".format(uuid()),
                exchange=hijack_exchange,
                routing_key="1",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )
            with Consumer(
                connection, on_message=on_response, queues=[hijack_queue], no_ack=True
            ):
                while True:
                    connection.drain_events()

    send_threads = []
    for i in range(1):
        send_threads.append(threading.Thread(target=sender, args=(chr(i + 97),)))
    recv_thread = threading.Thread(target=receiver, args=())

    for t in send_threads:
        t.start()
    recv_thread.start()

    for t in send_threads:
        t.join()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
