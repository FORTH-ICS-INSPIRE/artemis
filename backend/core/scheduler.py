from utils import get_logger, exception_handler, RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import time
import logging


log = logging.getLogger('artemis_logger')

class Scheduler(Service):


    def run_worker(self):
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except:
            log.exception('exception')
        finally:
            log.info('stopped')


    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.time_to_wait = 1 # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait_to_send_unhadled = 5

            self.db_clock_exchange = Exchange('db-clock', type='direct', durable=False, delivery_mode=1)

            self.db_clock_queue = Queue('scheduler-db-clock', exchange=self.db_clock_exchange, routing_key='db-clock', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 3})
            log.info('started')
            self._db_clock_send()

        def _get_module_status(self, module):
            self.response = None
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
            with Producer(self.connection) as producer:
                producer.publish(
                    {
                        'module': module,
                        'action': 'status'
                        },
                    exchange='',
                    routing_key='controller-queue',
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                )
            with Consumer(self.connection,
                          on_message=self._on_response,
                          queues=[callback_queue],
                          no_ack=True):
                while self.response is None:
                    self.connection.drain_events()
            if 'response' in self.response:
                if 'status' in self.response['response']:
                    if self.response['response']['status'] == 'up':
                        return True
            return False

        def _on_response(self, message):
            self.response = message.payload

        def _db_clock_send(self):
            unhandled_cnt = 0
            while 1:
                time.sleep(self.time_to_wait)
                self.producer.publish(
                    'bulk_operation',
                    exchange = self.db_clock_queue.exchange,
                    routing_key = self.db_clock_queue.routing_key,
                    retry = True,
                    declare = [self.db_clock_queue],
                    priority = 3
                )
                if(unhandled_cnt > 5 and self._get_module_status('detection')):
                    self.producer.publish(
                        'send_unhandled',
                        exchange = self.db_clock_queue.exchange,
                        routing_key = self.db_clock_queue.routing_key,
                        declare = [self.db_clock_queue],
                        retry = True,
                        priority = 2
                    )
                    unhandled_cnt = 0
                unhandled_cnt += 1


