import hashlib
import pickle
from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerProducerMixin
import json
import time
import traceback
import os
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
from utils import RABBITMQ_HOST

success_flag = False


class Worker(ConsumerProducerMixin):

    def __init__(self, connection):
        self.config = {
            'rules': [
                {
                    'prefixes': ['10.0.0.0/24', 'dead:beef::/32'],
                    'origin_asns': [1],
                    'neighbors': [2, 3, 4],
                    'mitigation': 'manual'
                }, {
                    'prefixes': ['10.0.0.0/24', 'dead:beef::/32'],
                    'origin_asns': [15],
                    'neighbors': [16, 17, 18],
                    'mitigation': 'manual'
                }, {
                    'prefixes': ['90.0.0.0/24'],
                    'origin_asns': [],
                    'neighbors': [],
                    'mitigation': 'manual'
                }
            ],
            'timestamp': 1
        }
        self.handled_counter = 0
        self.hijacks = {}
        self.pkts_test = 0
        self.connection = connection

        # EXCHANGES
        self.update_exchange = Exchange(
            'bgp-update',
            type='direct',
            durable=False,
            delivery_mode=1)
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)
        self.handled_exchange = Exchange(
            'handled-update',
            type='direct',
            durable=False,
            delivery_mode=1)

        # QUEUES
        self.config_request_queue = Queue(
            'config-request-queue',
            durable=False,
            max_priority=2,
            consumer_arguments={
                'x-priority': 2})
        self.update_queue = Queue('tester-update-update', exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                  consumer_arguments={'x-priority': 1})
        self.hijack_queue = Queue('tester-hijack-update', exchange=self.hijack_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                  consumer_arguments={'x-priority': 1})
        self.handled_queue = Queue('tester-hanlded-update', exchange=self.handled_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                   consumer_arguments={'x-priority': 1})

    def get_consumers(self, Consumer, channel):
        return [
            Consumer(
                queues=[self.config_request_queue],
                on_message=self.handle_config_request,
                # prefetch_count=1,
                no_ack=True
            ),
            Consumer(
                queues=[self.hijack_queue],
                on_message=self.handle_hijack,
                # prefetch_count=1,
                no_ack=True,
                accept=['pickle']
            ),
            Consumer(
                queues=[self.handled_queue],
                on_message=self.handle_handled_bgp_update,
                # prefetch_count=1,
                no_ack=True
            )
        ]

    def handle_config_request(self, message):
        self.producer.publish(
            self.config,
            exchange='',
            routing_key=message.properties['reply_to'],
            correlation_id=message.properties['correlation_id'],
            serializer='json',
            retry=True,
            priority=2
        )

        time.sleep(2)

        with open('tests/bgp_updates.json', 'r') as f:
            msgs = json.load(f)

        def key_generator(msg):
            msg['key'] = hashlib.md5(pickle.dumps([
                msg['prefix'],
                msg['path'],
                msg['type'],
                msg['service'],
                msg['timestamp']
            ])).hexdigest()

        for msg in msgs:
            key_generator(msg)
            self.producer.publish(
                msg,
                exchange=self.update_exchange,
                routing_key='update',
                serializer='json',
                declare=[self.update_queue]
            )

        # THROUGHPUT TEST
        self.pkts_test = 10000
        for i in range(self.pkts_test):
            msg = {
                'prefix': '10.0.0.0/24',
                'service': 'testing{}'.format(i),
                'type': 'A',
                'path': [9, 8, 7, 6, 5, 4, 1],
                'timestamp': 0
            }
            key_generator(msg)
            self.producer.publish(
                msg,
                exchange=self.update_exchange,
                routing_key='update',
                serializer='json',
                declare=[self.update_queue]
            )

    def handle_hijack(self, message):
        msg_ = message.payload
        self.hijacks[msg_['key']] = msg_

    def handle_handled_bgp_update(self, message):
        self.handled_counter += 1
        if self.handled_counter == 32 + self.pkts_test:
            # for name, hijack in self.hijacks.items():
            if len(self.hijacks) == 16:
                global success_flag
                success_flag = True
            self.should_stop = True


try:
    with Connection(RABBITMQ_HOST) as connection:
        worker = Worker(connection)
        worker.run()
except BaseException:
    traceback.print_exc()

if not success_flag:
    sys.exit(-1)
