#!/usr/bin/env python
import sys
import time
from kombu import Connection, Producer, Exchange, Queue
import os

obj = {"prefixes": {"forth_prefix_main": [], "forth_prefix_lamda": "139.91.250.0/24", "forth_prefix_vod": "139.91.2.0/24"}, "monitors": {"riperis": ["rrc01"]}, "asns": {"forth_asn": 8522, "grnet_forth_upstream": 5408, "lamda_forth_upstream_back": 56910, "vodafone_forth_upstream_back": 12361}, "rules": [{"prefixes": [["0.0.0.0/0", "::/0"]], "origin_asns": [8522], "neighbors": [5408, 12361], "mitigation": "manual"}, {"prefixes": ["139.91.250.0/24"], "origin_asns": [8522], "neighbors": [56910], "mitigation": "manual"}, {"prefixes": ["139.91.2.0/24"], "origin_asns": [8522], "neighbors": [12361], "mitigation": "manual"}]}

with Connection(os.getenv('RABBITMQ_HOST', 'localhost') as connection:
    exchange = Exchange('config', channel=connection, type='direct', durable=False, delivery_mode=1)
    exchange.declare()
    with Producer(connection) as producer:
        producer.publish(
                obj,
                exchange=exchange,
                routing_key='modify',
                serializer='json',
                priority=9)
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
