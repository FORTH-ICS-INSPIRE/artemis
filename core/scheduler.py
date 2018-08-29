from utils import log, exception_handler, RABBITMQ_HOST
from multiprocessing import Process
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
from setproctitle import setproctitle
import traceback


class Scheduler(Process):


    def __init__(self):
        super().__init__()
        self.worker = None
        self.stopping = False


    def run(self):
        setproctitle(self.name)
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            traceback.print_exc()
        if self.worker is not None:
            self.worker.stop()
        log.info('Scheduler Stopped..')
        self.stopping = True


    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True
            while(self.stopping):
                time.sleep(1)


    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.flag = False
            self.time_to_wait = 1 # Time in secs to gather entries to perform a bulk operation

            self.db_clock_exchange = Exchange('db_clock', type='direct', durable=False, delivery_mode=1)

            self.flag = True
            log.info('Scheduler Started..')
            self.db_clock_send()

        def db_clock_send(self):
            while 1:
                time.sleep(self.time_to_wait)
                self.producer.publish(
                    'proceed',
                    exchange = self.db_clock_exchange,
                    routing_key = 'db_clock',
                    retry = True,
                    priority = 3
                )



