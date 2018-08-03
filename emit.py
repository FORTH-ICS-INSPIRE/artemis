#!/usr/bin/env python
import pika
import sys
import pickle
from utils.mq import AsyncConnection
import threading
import time

publisher = AsyncConnection(exchange='bgp_update',
        objtype='publisher',
        routing_key='update',
        exchange_type='direct')

threading.Thread(target=publisher.run, args=()).start()

obj = {"type":"A", "as_path": [0,1,2,3], "prefix": "139.91.0.0/24", "timestamp": int(sys.argv[1])}

publisher.publish_message(obj)
publisher.stop()
