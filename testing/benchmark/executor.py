import os
import sys
import time
from multiprocessing import Process

import requests
import ujson as json
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import serialization
from kombu import uuid

serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)

# global vars
CONFIGURATION_HOST = "configuration"
DATABASE_HOST = "database"
DATA_WORKER_DEPENDENCIES = [
    "configuration",
    "database",
    "detection",
    "fileobserver",
    "prefixtree",
]
REST_PORT = 3000
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)

if len(sys.argv) == 2:
    LIMIT_UPDATES = int(sys.argv[1])
else:
    LIMIT_UPDATES = 65536

if LIMIT_UPDATES > 65536:
    print("Cannot support more that 65536 updates at the moment")
    sys.exit()


def wait_data_worker_dependencies(data_worker_dependencies):
    while True:
        met_deps = set()
        unmet_deps = set()
        for service in data_worker_dependencies:
            try:
                r = requests.get("http://{}:{}/health".format(service, REST_PORT))
                status = True if r.json()["status"] == "running" else False
                if not status:
                    unmet_deps.add(service)
                else:
                    met_deps.add(service)
            except Exception:
                print(
                    "exception while waiting for service '{}'. Will retry".format(
                        service
                    )
                )
        if len(unmet_deps) == 0:
            print(
                "all needed data workers started: {}".format(data_worker_dependencies)
            )
            break
        else:
            print(
                "'{}' data workers started, waiting for: '{}'".format(
                    met_deps, unmet_deps
                )
            )
        time.sleep(1)


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
                        msg_,
                        exchange=exchange,
                        routing_key="update",
                        serializer="ujson",
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
                if recv_cnt % 1000 == 0:
                    with open("{}-{}".format(exchange_name, routing_key), "w") as f:
                        print(
                            "[!] Throughput for {} on {}:{} = {} msg/s".format(
                                recv_cnt,
                                exchange_name,
                                routing_key,
                                recv_cnt / (time.time() - start),
                            )
                        )
                        f.write(str(int(recv_cnt / (time.time() - start))))
        stop = time.time()
        print(
            "[!] Throughput for {} on {}:{} = {} msg/s".format(
                recv_cnt, exchange_name, routing_key, recv_cnt / (stop - start)
            )
        )
        with open("{}-{}".format(exchange_name, routing_key), "w") as f:
            f.write(str(int(recv_cnt / (stop - start))))

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

    # wait for dependencies data workers to start
    wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

    precvs = [
        Process(target=receive, args=("amq.direct", "update-insert")),
        Process(target=receive, args=("amq.direct", "update-update")),
        Process(target=receive, args=("amq.direct", "hijack-update")),
        Process(target=receive, args=("bgp-update", "update")),
        Process(target=receive, args=("hijack-update", "update")),
    ]
    psend = Process(target=send, args=())

    for precv in precvs:
        precv.start()
    time.sleep(1)
    psend.start()

    for precv in precvs:
        precv.join()
    psend.join()
    print("[+] Exiting")
