from utils import RABBITMQ_HOST, get_logger
from kombu import Connection, Exchange
from kombu.mixins import ConsumerProducerMixin
import time
import signal
from xmlrpc.client import ServerProxy


log = get_logger()


class Scheduler():

    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            log.exception('exception')
        finally:
            log.info('stopped')

    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True

    # TODO this worker is not consumer we need to change class
    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.time_to_wait = 1  # Time in secs to gather entries to perform a bulk operation
            self.time_to_wait_to_send_unhadled = 5

            self.db_clock_exchange = Exchange(
                'db-clock',
                type='direct',
                channel=connection,
                durable=False,
                delivery_mode=1)
            self.db_clock_exchange.declare()
            log.info('started')
            self._db_clock_send()

        def _get_module_status(self, module):
            server = ServerProxy('http://localhost:9001/RPC2')
            response = server.supervisor.getProcessInfo(module)
            return response['state'] == 20

        def _db_clock_send(self):
            unhandled_cnt = 0
            while True:
                time.sleep(self.time_to_wait)
                self.producer.publish(
                    'bulk_operation',
                    exchange=self.db_clock_exchange,
                    routing_key='db-clock-message',
                    retry=True,
                    priority=3
                )
                if (unhandled_cnt % 5) == 0:
                    if self._get_module_status('detection'):
                        self.producer.publish(
                            'send_unhandled',
                            exchange=self.db_clock_exchange,
                            routing_key='db-clock-message',
                            retry=True,
                            priority=2
                        )
                        unhandled_cnt = 0
                unhandled_cnt += 1


if __name__ == '__main__':
    service = Scheduler()
    service.run()
