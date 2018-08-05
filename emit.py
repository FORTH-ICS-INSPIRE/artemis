#!/usr/bin/env python
import sys
import time
from kombu import Connection, Producer, Exchange, Queue

exchange = Exchange('bgp_update', type='fanout', durable=False)
queue = Queue('bgp_queue', exchange)
obj = {"type":"A", "path": [0,1,2,3], "prefix": "139.91.0.0/24", "peer_asn": 0, "timestamp": 0}

with Connection('amqp://guest:guest@localhost:5672//') as connection:
    producer = Producer(connection)

    producer.publish(
            obj,
            exchange=queue.exchange,
            routing_key=queue.routing_key,
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
