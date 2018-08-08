#!/usr/bin/env python
import sys
import time
from kombu import Connection, Producer, Exchange, Queue
import os

exchange = Exchange('bgp_update', type='direct', durable=False, delivery_mode=1)
obj = {"type":"A", "path": [0,1,2,3], "prefix": "139.91.0.0/24", "peer_asn": 0, "timestamp": 0}

with Connection(os.getenv('RABBITMQ_HOST', 'localhost') as connection:
    with Producer(connection) as producer:
        producer.publish(
                obj,
                exchange=exchange,
                routing_key='update',
                serializer='json')
# threads = []
#
# for _ in range(10):
#     threads.append(threading.Thread(target=start, args=()))
#
# for i in range(10):
#     threads[i].start()
#
# for i in range(10):
#     threads[i].join()
