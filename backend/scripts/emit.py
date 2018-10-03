#!/usr/bin/env python
from kombu import Connection, Producer, Exchange
import os
import threading


def start(tid):
    obj = {
        "orig_path": [],
        "communities": [],
        "key": "1",
        "service": "a",
        "type": "A",
        "path": [
            5408,
            8522],
        "prefix": "139.91.0.0/16",
        "peer_asn": 8522,
        "timestamp": 0}

    with Connection(os.getenv('RABBITMQ_HOST', 'localhost')) as connection:
        exchange = Exchange(
            'bgp-update',
            channel=connection,
            type='direct',
            durable=False,
            delivery_mode=1)
        exchange.declare()
        with Producer(connection) as producer:
            for i in range(1000):
                obj['key'] = '{}-{}'.format(i, tid)
                obj['timestamp'] = i
                producer.publish(
                    obj,
                    exchange=exchange,
                    routing_key='update',
                    serializer='json')


threads = []

for i in range(10):
    threads.append(threading.Thread(target=start, args=(i,)))

for i in range(10):
    threads[i].start()

for i in range(10):
    threads[i].join()
