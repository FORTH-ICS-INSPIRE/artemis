from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
from webapp.utils import log, exception_handler, RABBITMQ_HOST
from webapp.utils.conf import Config


class Resolve_hijack():

    def __init__(self, hijack_key):
        self.connection = None
        self.hijack_key = hijack_key
        self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
        self.init_conn()


    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.info('Resolve_hijack failed to connect to rabbitmq..')

    def resolve(self):
        with Producer(self.connection) as producer:
            producer.publish(
                self.hijack_key,
                exchange=self.hijack_exchange,
                routing_key='resolved',
                priority=2
            )

class Mitigate_hijack():

    def __init__(self, hijack_key, prefix):
        self.connection = None
        self.hijack_key = hijack_key
        self.prefix = prefix
        self.mitigation_exchange = Exchange('mitigation', type='direct', durable=False, delivery_mode=1)
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.info('Resolve_hijack failed to connect to rabbitmq..')

    def mitigate(self):
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                    'prefix': self.prefix
                },
                exchange=self.mitigation_exchange,
                routing_key='mitigate',
                priority=2
            )