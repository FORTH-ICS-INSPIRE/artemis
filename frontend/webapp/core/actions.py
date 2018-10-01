from kombu import Connection, Exchange, Consumer, Producer, Queue, uuid
from webapp.utils import RABBITMQ_HOST
from webapp.utils.conf import Config
import logging
import difflib

log = logging.getLogger('webapp_logger')


class Resolve_hijack():

    def __init__(self, hijack_key):
        self.connection = None
        self.hijack_key = hijack_key
        self.init_conn()
        self.hijack_exchange = Exchange('hijack-update', type='direct', durable=False, delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.error('Resolve_hijack failed to connect to rabbitmq..')

    def resolve(self):
        log.debug("send resolve hijack message with key: {}".format(self.hijack_key))
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                },
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
            log.error('Resolve_hijack failed to connect to rabbitmq..')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def mitigate(self):
        log.debug("sending mitigate message")
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

class Ignore_hijack():

    def __init__(self, hijack_key):
        self.connection = None
        self.hijack_key = hijack_key
        self.init_conn()
        self.hijack_exchange = Exchange('hijack-update', type='direct', durable=False, delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.error('Ignore_hijack failed to connect to rabbitmq..')

    def ignore(self):
        log.debug("sending ignore message")
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                },
                exchange=self.hijack_exchange,
                routing_key='ignored',
                priority=2
            )

class New_config():

    def __init__(self):
        self.connection = None
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.error('New_config failed to connect to rabbitmq..')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def send(self, new_config, old_config):

        changes = ''.join(difflib.unified_diff(new_config, old_config))
        if len(changes) > 0:
            self.response = None
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
            with Producer(self.connection) as producer:
                producer.publish(
                    new_config,
                    exchange='',
                    routing_key='config-modify-queue',
                    serializer='yaml',
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id
                )
            with Consumer(self.connection,
                    on_message=self.on_response,
                    queues=[callback_queue],
                    no_ack=True):
                while self.response is None:
                    self.connection.drain_events()

            if self.response['status'] == 'accepted':
                text = 'new configuration accepted:\n{}'.format(changes)
                log.info(text)
                return 'Configuration file updated.', True
            else:
                log.error('invalid configuration:\n{}'.format(new_config))
                return "Invalid configuration file.\n{}".format(self.response['reason']), False
        else:
            return "No changes found on the new configuration.", False











