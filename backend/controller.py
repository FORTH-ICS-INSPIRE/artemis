import os
import signal
import time
from core.configuration import Configuration
from core.monitor import Monitor
from core.detection import Detection
from core.mitigation import Mitigation
from core.scheduler import Scheduler
from core.postgresql_db import Postgresql_db
from utils import log, RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid
from kombu.mixins import ConsumerProducerMixin


class Controller(Service):


    def run_worker(self):
        with Connection(RABBITMQ_HOST) as connection:
            self.worker = self.Worker(connection)
            self.worker.run()
        # Stop all modules and web application
        for name, module in self.worker.modules.items():
            if module.is_running():
                module.stop(block=True)
        log.info('Bye..!')


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection
            # Instatiate Modules
            self.modules = {}

            self.modules['configuration'] = Configuration()
            self.modules['scheduler'] = Scheduler()
            self.modules['monitor'] = Monitor()
            self.modules['detection'] = Detection()
            self.modules['mitigation'] = Mitigation()
            self.modules['postgresql_db'] = Postgresql_db()


            # for name, module in modules.items():
            #     if not module.is_running():
            #         module.start()
            #
            # QUEUES
            self.controller_queue = Queue('controller_queue', routing_key='action', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})

            log.info('Controller Started..')


        def get_consumers(self, Consumer, channel):
            return [
                    Consumer(
                        queues=[self.controller_queue],
                        on_message=self.controller_handler,
                        prefetch_count=1,
                        no_ack=True
                        )
                    ]


        def controller_handler(self, message):
            log.info(' [x] Controller - Received an action request')

            respose = ''
            if message.payload['module'] in modules:
                name = message.payload['module']
                module = modules[name]
                if message.payload['action'] == 'stop':
                    if not module.is_running():
                        response = '{} already stopped'.format(name)
                    else:
                        module.stop(block=True)
                        respose = '{} stopped'.format(name)
                elif message.payload['action'] == 'start':
                    if module.is_running():
                        response = '{} already running'.format(name)
                    else:
                        modules[message.payload['module']].start()
                        response = '{} started'.format(name)
                elif message.payload['action'] == 'status':
                    if module.is_running():
                        response = '{} is running'.format(name)
                    else:
                        response = '{} is not running'.format(name)
            else:
                response = '{} is not registered'.format(name)

            self.producer.publish(
                response,
                exchange='',
                routing_key = message.properties['reply_to'],
                correlation_id = message.properties['correlation_id'],
                retry = True,
                priority = 2
            )




if __name__ == '__main__':
    c = Controller()
    c.start()
