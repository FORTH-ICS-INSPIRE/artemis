from utils import log, exception_handler, RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import time
import traceback

class Scheduler(Service):


    def run_worker(self):
        with Connection(RABBITMQ_HOST) as connection:
            self.worker = self.Worker(connection)
            self.worker.run()
        if self.worker is not None:
            self.worker.stop()
        log.info('Scheduler Stopped..')


    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.flag = False
            self.time_to_wait = 1 # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait_to_send_unhadled = 5

            self.db_clock_exchange = Exchange('db_clock', type='direct', durable=False, delivery_mode=1)

            self.db_clock_queue = Queue(uuid(), exchange=self.db_clock_exchange, routing_key='db_clock', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 3})
            self.flag = True
            log.info('Scheduler Started..')
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


