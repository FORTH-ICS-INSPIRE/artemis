import radix
import subprocess
from utils import log, RABBITMQ_HOST
from multiprocessing import Process
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
from setproctitle import setproctitle
import traceback

class Mitigation(Process):

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
        log.info('Mitigation Stopped..')
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
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None

            # EXCHANGES
            self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
            self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.callback_queue = Queue(uuid(), durable=False, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})

            self.config_request_rpc()
            self.flag = True
            log.info('Mitigation Started..')


        def get_consumers(self, Consumer, channel):
            return [
                    Consumer(
                        queues=[self.config_queue],
                        on_message=self.handle_config_notify,
                        prefetch_count=1,
                        no_ack=True
                        )
                    ]


        def handle_config_notify(self, message):
            log.info(' [x] Mitigation - Config Notify')
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.init_mitigation()


        def config_request_rpc(self):
            self.correlation_id = uuid()

            self.producer.publish(
                '',
                exchange = '',
                routing_key = 'config_request_queue',
                reply_to = self.callback_queue.name,
                correlation_id = self.correlation_id,
                retry = True,
                declare = [self.callback_queue, Queue('config_request_queue', durable=False, max_priority=2)],
                priority = 2
            )
            with Consumer(self.connection,
                        on_message=self.handle_config_request_reply,
                        queues=[self.callback_queue],
                        no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()


        def handle_config_request_reply(self, message):
            log.info(' [x] Mitigation - Received Configuration')
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                if raw['timestamp'] > self.timestamp:
                    self.timestamp = raw['timestamp']
                    self.rules = raw.get('rules', [])
                    self.init_mitigation()


        def init_mitigation(self):
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                for prefix in rule['prefixes']:
                    node = self.prefix_tree.add(prefix)
                    node.data['mitigation'] = rule['mitigation']


