#!/usr/bin/env python
import pika
import sys
import pickle
from utils.mq import AsyncConnection
import threading
import time

def start():
    publisher = AsyncConnection(exchange='bgp_update',
            objtype='publisher',
            routing_key='update',
            exchange_type='direct')

    publisher.start()

    obj = {"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": 0}

    for _ in range(10000):
        publisher.publish_message(pickle.dumps(obj))

    publisher.stop()

threads = []

for _ in range(10):
    threads.append(threading.Thread(target=start, args=()))

for i in range(10):
    threads[i].start()

for i in range(10):
    threads[i].join()
