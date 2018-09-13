from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
from webapp.utils import log, exception_handler, RABBITMQ_HOST
from webapp.utils.conf import Config


class Modules_status():

    def __init__(self):
        self.connection = None
        self.response = None
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.info('Modules_status failed to connect to rabbitmq..')

    def call(self, module, action):
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'module': module,
                    'action': action
                    },
                exchange='',
                routing_key='controller_queue',
                declare=[callback_queue],
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
            )
        with Consumer(self.connection,
                      on_message=self.on_response,
                      queues=[callback_queue],
                      no_ack=True):
            while self.response is None:
                self.connection.drain_events()

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def get_response_all(self):
        ret_response = {}
        if 'response' in self.response:
            if self.response['response']['result'] == 'success':
                for module in ['configuration', 'scheduler', 'postgresql_db', 'monitor', 'detection', 'mitigation']:
                    ret_response[module] = self.response['response'][module]
        return ret_response