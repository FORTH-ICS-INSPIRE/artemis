from utils import RABBITMQ_HOST, get_logger, SUPERVISOR_HOST, SUPERVISOR_PORT
from kombu import Connection, Exchange, Producer
import time
from xmlrpc.client import ServerProxy


log = get_logger()


class Scheduler():

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
        except KeyboardInterrupt:
            pass
        finally:
            log.info('stopped')

    class Worker():

        def __init__(self, connection):
            self.connection = connection
            self.time_to_wait = 1  # Time in secs to gather entries to perform a bulk operation

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
            server = ServerProxy(
                'http://{}:{}/RPC2'.format(SUPERVISOR_HOST, SUPERVISOR_PORT))
            try:
                return any([x['name'] for x in server.supervisor.getAllProcessInfo()
                            if x['group'] == module and x['state'] == 20])
            except BaseException:
                return False

        def _db_clock_send(self):
            with Producer(self.connection) as producer:
                while True:
                    time.sleep(self.time_to_wait)
                    producer.publish(
                        {'op': 'bulk_operation'},
                        exchange=self.db_clock_exchange,
                        routing_key='pulse',
                        retry=True,
                        priority=3
                    )


def run():
    service = Scheduler()
    service.run()


if __name__ == '__main__':
    run()
