#!/usr/bin/env python
import pika
import sys
import pickle


connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

channel.exchange_declare(exchange='bgp_update',
                         exchange_type='direct')

obj = {"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": int(sys.argv[1])}
channel.basic_publish(exchange='bgp_update',
                      routing_key='update',
                      body=pickle.dumps(obj))
connection.close()
