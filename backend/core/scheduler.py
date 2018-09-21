from utils import get_logger, exception_handler, RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import time


log = get_logger(__name__)

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
            self.db_clock_send()

        def db_clock_send(self):
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
                if(unhandled_cnt == 5):
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


