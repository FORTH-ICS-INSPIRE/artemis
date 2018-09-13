from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
from webapp.utils import log, exception_handler, RABBITMQ_HOST
from webapp.utils.conf import Config


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
                routing_key = 'config_request_queue',
                reply_to = callback_queue.name,
                correlation_id = self.correlation_id,
                retry = True,
                declare = [callback_queue, Queue('config_request_queue', durable=False, max_priority=2)],
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


class Configuration_notifier():

    def __init__(self, conf_share):
        self.conf_share = conf_share

    def run_worker(self):
        with Connection(RABBITMQ_HOST) as connection:
            self.worker = self.Worker(connection, self.conf_share)
            self.worker.run()

    class Worker(ConsumerProducerMixin):

        def __init__(self, connection, conf_share):
            self.connection = connection
            self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)
            self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.conf_share = conf_share
            log.info('Configuration_notifier Started..')

        def config_request_rpc(self):
                self.correlation_id = uuid()
                callback_queue = Queue(uuid(), durable=False, max_priority=2,
                        consumer_arguments={'x-priority': 2})
                self.producer.publish(
                    '',
                    exchange = '',
                    routing_key = 'config_request_queue',
                    reply_to = callback_queue.name,
                    correlation_id = self.correlation_id,
                    retry = True,
                    declare = [callback_queue, Queue('config_request_queue', durable=False, max_priority=2)],
                    priority = 2
                )
                with Consumer(self.connection,
                            on_message=self.handle_config_request_reply,
                            queues=[callback_queue],
                            no_ack=True):
                    while self.rules is None:
                        self.connection.drain_events()

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    no_ack=True
                    ),
            ]

        def handle_config_notify(self, message):
            log.info(' [x] Webapp - Config Notify')
            raw = message.payload
            self.conf_share = raw