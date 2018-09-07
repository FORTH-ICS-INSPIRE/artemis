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

        log.info('Controller Stopped..')


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection
            # Instatiate Modules
            self.modules = {}

            # Required Modules
            self.modules['configuration'] = Configuration()
            self.modules['configuration'].start()

            # Optional Modules
            self.modules['scheduler'] = Scheduler()
            self.modules['postgresql_db'] = Postgresql_db()
            self.modules['monitor'] = Monitor()
            self.modules['detection'] = Detection()
            self.modules['mitigation'] = Mitigation()

            # QUEUES
            self.controller_queue = Queue('controller_queue')

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

            response = {}
            if message.payload['module'] in self.modules:
                name = message.payload['module']
                module = self.modules[name]
                if message.payload['action'] == 'stop':
                    if not module.is_running():
                        response = {'result': 'fail',
                                'reason': 'already stopped'}
                    else:
                        module.stop(block=True)
                        response = {'result': 'success'}
                elif message.payload['action'] == 'start':
                    if module.is_running():
                        response = {'result': 'fail',
                                'reason': 'already running'}
                    else:
                        self.modules[message.payload['module']] = module.__class__()
                        self.modules[message.payload['module']].start()
                        response = {'result': 'success'}
                elif message.payload['action'] == 'status':
                    if module.is_running():
                        response = {'result': 'success', 'status': 'up'}
                    else:
                        response = {'result': 'success', 'status': 'down'}
                else:
                    response = {'result': 'fail', 'reason': 'unknown action'}
            elif message.payload['module'] == 'all':
                if message.payload['action'] == 'stop':
                    for name, module in self.modules.items():
                        if module.is_running():
                            module.stop()
                    response = {'result': 'success'}
                elif message.payload['action'] == 'start':
                    for name, module in self.modules.items():
                        if not module.is_running():
                            module.start()
                    response = {'result': 'success'}
                elif message.payload['action'] == 'status':
                    response = {'result': 'success'}
                    for name, module in self.modules.items():
                        if module.is_running():
                            response[name] = 'up'
                        else:
                            response[name] = 'down'
                else:
                    response = {'result': 'fail', 'reason': 'unknown action'}
            else:
                response = {'result': 'fail',
                        'reason': 'not registered module'}

            message.payload['response'] = response
            self.producer.publish(
                message.payload,
                exchange='',
                routing_key = message.properties['reply_to'],
                correlation_id = message.properties['correlation_id'],
                retry = True,
                priority = 2
            )

if __name__ == '__main__':
    c = Controller()
    c.start()
