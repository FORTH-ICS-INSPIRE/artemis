import threading

from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import uuid
from utils import get_logger
from utils import RABBITMQ_URI

import sys

log = get_logger()

if len(sys.argv) == 2:
    LIMIT_UPDATES = int(sys.argv[1])
else:
    LIMIT_UPDATES = 65536

if LIMIT_UPDATES > 65536:
    print('Cannot support more that 65536 updates at the moment')
    sys.exit()

def sender():
    send_cnt = 0
    msg_ = {
        "orig_path": [],
        "communities": [],
        "service": "a",
        "type": "A",
        "path": [8, 4, 3, 2, 1],
        "peer_asn": 8,
    }
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
                        serializer="json",
                    )
                    send_cnt += 1
                    print("Total send {}\r".format(send_cnt))


if __name__ == "__main__":
    try:
        sender()
    except Exception as e:
        print("Exception: {}".format(e))
    except KeyboardInterrupt:
        pass
