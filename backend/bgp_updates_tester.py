from kombu import Connection, Producer, Exchange, Queue, uuid
from kombu.mixins import ConsumerProducerMixin
from utils import RABBITMQ_HOST
import json
import traceback


class Worker(ConsumerProducerMixin):
    def __init__(self, connection):
        self.connection = connection

        # EXCHANGES
        self.update_exchange = Exchange('bgp_update', type='direct', durable=False, delivery_mode=1)
        self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
        self.handled_exchange = Exchange('handled_update', type='direct', durable=False, delivery_mode=1)

        # QUEUES
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
                    ),
                ]


    def handle_hijack(self, message):
        msg_ = message.payload
        print(msg_)


    def handle_handled_bgp_update(self, message):
        msg_ = message.payload
        print(msg_)

try:
    with Connection(RABBITMQ_HOST) as connection:
        worker = Worker(connection)
        worker.run()

except:
    traceback.print_exc()
