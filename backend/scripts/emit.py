#!/usr/bin/env python
from kombu import Connection, Producer, Exchange
import os
import threading
import time
import json


def start(tid):
    with open('bgp_update.json', 'r') as f:
        objs = json.load(f)

    with Connection(os.getenv('RABBITMQ_HOST', 'localhost')) as connection:
        exchange = Exchange(
            'bgp-update',
            channel=connection,
            type='direct',
            durable=False,
            delivery_mode=1)
        exchange.declare()
        with Producer(connection) as producer:
            for obj in objs:
                time.sleep(1)
                if 'key' not in obj:
                    obj['key'] = '{}'.format(time.time())
                if 'timestamp' not in obj:
                    obj['timestamp'] = time.time()
                producer.publish(
                    obj,
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
