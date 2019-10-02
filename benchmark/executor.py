import os
import sys
import time
from multiprocessing import Process
from xmlrpc.client import ServerProxy

from kombu import Connection
from kombu import Exchange
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


if len(sys.argv) == 2:
    LIMIT_UPDATES = int(sys.argv[1])
else:
    LIMIT_UPDATES = 65536

if LIMIT_UPDATES > 65536:
    print("Cannot support more that 65536 updates at the moment")
    sys.exit()


def wait():
    ctx = ServerProxy(BACKEND_SUPERVISOR_URI)

    try:
        state = ctx.supervisor.getProcessInfo("detection")["state"]
        while state == 10:
            print("[!] Waiting for Detection")
            time.sleep(0.5)
            state = ctx.supervisor.getProcessInfo("detection")["state"]
    except Exception as e:
        print(e)
        sys.exit(-1)
    print("[!] Detection is running")


def send():
    send_cnt = 0
    msg_ = {
        "orig_path": [],
        "communities": [],
        "service": "a",
        "type": "A",
        "path": [8, 4, 3, 2, 1],
        "peer_asn": 8,
    }

    print("[+] Sending {}".format(LIMIT_UPDATES))
    with Connection(RABBITMQ_URI) as connection:
        exchange = Exchange(
            "bgp-update", channel=connection, type="direct", durable=False
        )
        exchange.declare()
        with Producer(connection) as producer:
            for x in range(0, 256):
                if send_cnt // LIMIT_UPDATES > 0:
                    break
                for y in range(0, 256):
                    if send_cnt // LIMIT_UPDATES > 0:
                        break
                    msg_["timestamp"] = x * 1000 + y
                    msg_["key"] = "{}-{}".format(x, y)
                    msg_["prefix"] = "10.{}.{}.0/24".format(x, y)
                    producer.publish(
                        msg_, exchange=exchange, routing_key="update", serializer="json"
                    )
                    send_cnt += 1
    print("[+] Exit send")


def receive(exchange_name, routing_key):
    def bind_and_wait(connection, queue):
        queue.declare(channel=connection.default_channel)
        bind_queue = queue.bind(connection.default_channel)

        recv_cnt = 0
        start = time.time()
        while recv_cnt < LIMIT_UPDATES:
            if bind_queue.get():
                recv_cnt += 1
        stop = time.time()
        print(
            "[!] Throughput for {} on {}:{} = {} msg/s".format(
                recv_cnt, exchange_name, routing_key, LIMIT_UPDATES / (stop - start)
            )
        )

    print("[+] Receiving {} on {}:{}".format(LIMIT_UPDATES, exchange_name, routing_key))
    with Connection(RABBITMQ_URI) as connection:
        exchange = Exchange(
            exchange_name,
            channel=connection,
            type="direct",
            durable=False,
            delivery_mode=1,
        )
        exchange.declare()
        queue = Queue(
            "{}".format(uuid()),
            exchange=exchange,
            routing_key=routing_key,
            durable=False,
            auto_delete=True,
            max_priority=1,
            consumer_arguments={"x-priority": 1},
            channel=connection.default_channel,
        )
        bind_and_wait(connection, queue)
    print("[+] Exit recv")


if __name__ == "__main__":
    print("[+] Starting")
    wait()

    precv0 = Process(target=receive, args=("bgp-update", "update"))
    # precv1 = Process(target=receive, args=("handled-update", "update"))
    precv2 = Process(target=receive, args=("hijack-update", "update"))
    psend = Process(target=send, args=())

    precv0.start()
    # precv1.start()
    precv2.start()
    time.sleep(1)
    psend.start()

    precv0.join()
    # precv1.join()
    precv2.join()
    psend.join()
    print("[+] Exiting")
