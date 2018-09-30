from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
from webapp.utils import RABBITMQ_HOST
from webapp.utils.conf import Config
import logging


log = logging.getLogger('webapp_logger')

class Configuration_request():

    def __init__(self):
        self.connection = None
        self.conf = None
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.info('Configuration_request failed to connect to rabbitmq..')

    def config_request_rpc(self):
        log.info("Config request..")
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(), durable=False, max_priority=2,
                consumer_arguments={'x-priority': 2})
        with Producer(self.connection) as producer:
            producer.publish(
                '',
                exchange = '',
                routing_key = 'config-request-queue',
                reply_to = callback_queue.name,
                correlation_id = self.correlation_id,
                retry = True,
                declare = [callback_queue, Queue('config-request-queue', durable=False, max_priority=2)],
                priority = 2
            )
        with Consumer(self.connection,
                    on_message=self.handle_config_request_reply,
                    queues=[callback_queue],
                    no_ack=True):
            while self.conf is None:
                self.connection.drain_events()
    
    def handle_config_request_reply(self, message):
        log.info(' [x] Webapp - Received Configuration')
        if self.correlation_id == message.properties['correlation_id']:
            self.conf = Config(message.payload)

    def get_conf(self):
        return self.conf