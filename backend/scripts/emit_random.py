#!/usr/bin/env python
from kombu import Connection, Producer, Exchange
import os
import threading
import time
import json


def start(tid):
    _id = time.time()
    update = {
        "key": "{}-{}".format(_id, tid),
        "timestamp": int(_id),
        "orig_path": [],
        "communities": [],
        "service": "a",
        "type": "A",
        "path": [1, 2, 3, 4, int(_id) % 100],
        "prefix": "139.91.0.0/16",
        "peer_asn": 1
    }
    with Connection(os.getenv('RABBITMQ_HOST', 'localhost')) as connection:
        exchange = Exchange(
            'bgp-update',
            channel=connection,
            type='direct',
            durable=False,
            delivery_mode=1)
        exchange.declare()
        with Producer(connection) as producer:
            producer.publish(
                update,
                exchange=exchange,
                routing_key='update',
                serializer='json')

start(0)
# threads = []
#
# for i in range(10):
#     threads.append(threading.Thread(target=start, args=(i,)))
#
# for i in range(10):
#     threads[i].start()
#
# for i in range(10):
#     threads[i].join()
