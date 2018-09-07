from kombu import Connection, Producer, Exchange, Queue, uuid
from kombu.mixins import ConsumerProducerMixin
from utils import RABBITMQ_HOST
import json
import traceback


class Worker(ConsumerProducerMixin):

    def __init__(self, connection):
        self.config = {
                'rules': [
                    {
                        'prefixes': ['10.0.0.0/24'],
                        'origin_asns': [1],
                        'neighbors': [2, 3, 4],
                        'mitigation': 'manual'
                    },{
                        'prefixes': ['10.0.0.0/24'],
                        'origin_asns': [15],
                        'neighbors': [16, 17, 18],
                        'mitigation': 'manual'
                    },{
                        'prefixes': ['90.0.0.0/24'],
                        'origin_asns': [],
                        'neighbors': [],
                        'mitigation': 'manual'
                    },{
                        'prefixes': ['deaf:beef::/32'],
                        'origin_asns': [1],
                        'neighbors': [2, 3, 4],
                        'mitigation': 'manual'
                    },{
                        'prefixes': ['deaf:beef::/32'],
                        'origin_asns': [15],
                        'neighbors': [16, 17, 18],
                        'mitigation': 'manual'
                    }],
                'timestamp': 1
        }
        self.handled_counter = 0
        self.hijacks_counter = 0
        self.connection = connection

        # EXCHANGES
        self.update_exchange = Exchange('bgp_update', type='direct', durable=False, delivery_mode=1)
        self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
        self.handled_exchange = Exchange('handled_update', type='direct', durable=False, delivery_mode=1)

        # QUEUES
        self.config_request_queue = Queue('config_request_queue', durable=False, max_priority=2, consumer_arguments={'x-priority': 2})
        self.update_queue = Queue(uuid(), exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                consumer_arguments={'x-priority': 1})
        self.hijack_queue = Queue(uuid(), exchange=self.hijack_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                consumer_arguments={'x-priority': 1})
        self.handled_queue = Queue(uuid(), exchange=self.handled_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                consumer_arguments={'x-priority': 1})

        with open('bgp_updates.json', 'r') as f:
            msgs = json.load(f)

        for msg in msgs:
            self.producer.publish(
                msg,
                exchange=self.update_exchange,
                routing_key='update',
                serializer='json'
            )


    def get_consumers(self, Consumer, channel):
        return [
                Consumer(
                    queues=[self.config_request_queue],
                    on_message=self.handle_config_request,
                    prefetch_count=1,
                    no_ack=True
                    ),
                Consumer(
                    queues=[self.hijack_queue],
                    on_message=self.handle_hijack,
                    prefetch_count=1,
                    no_ack=True,
                    accept=['pickle']
                    ),
                Consumer(
                    queues=[self.handled_queue],
                    on_message=self.handle_handled_bgp_update,
                    prefetch_count=1,
                    no_ack=True
                    )
                ]


    def handle_config_request(self, message):
        log.info(' [x] Configuration - Received configuration request')
        self.producer.publish(
            self.config,
            exchange='',
            routing_key = message.properties['reply_to'],
            correlation_id = message.properties['correlation_id'],
            serializer = 'json',
            retry = True,
            priority = 2
        )


    def handle_hijack(self, message):
        msg_ = message.payload
        log.info(msg_)
        self.hijacks_counter += 1


    def handle_handled_bgp_update(self, message):
        self.handled_counter += 1
        if self.handled_counter == 37:
            self.should_stop = True

try:
    with Connection(RABBITMQ_HOST) as connection:
        worker = Worker(connection)
        worker.run()
except:
    traceback.print_exc()
