from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
from utils import log, exception_handler, RABBITMQ_HOST


class Configuration(ConsumerProducerMixin):

    def __init__(self):
        self.connection = None

        self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)

        self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                consumer_arguments={'x-priority': 2})

        self.init_conn()


	def init_conn(self):
		self.connection = Connection(os.getenv('RABBITMQ_HOST', 'localhost'))

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
        log.info(' [x] PostgreSQL_db - Config Notify')
        raw = message.payload