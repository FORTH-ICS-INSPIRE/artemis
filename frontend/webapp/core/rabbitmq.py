from kombu import Connection, Queue, uuid, Consumer, Producer
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
        except BaseException:
            log.info('Configuration_request failed to connect to rabbitmq..')

    def config_request_rpc(self):
        log.info("Config request..")
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(),
                               durable=False,
                               exclusive=True,
                               auto_delete=True,
                               max_priority=4,
                               consumer_arguments={
            'x-priority': 4})
        with Producer(self.connection) as producer:
            producer.publish(
                '',
                exchange='',
                routing_key='config-request-queue',
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        'config-request-queue',
                        durable=False,
                        max_priority=4,
                        consumer_arguments={
                            'x-priority': 4}),
                    callback_queue
                ],
                priority=4
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
