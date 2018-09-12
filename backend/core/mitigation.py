import radix
import subprocess
from utils import log, RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import time
import traceback

class Mitigation(Service):


    def run_worker(self):
        with Connection(RABBITMQ_HOST) as connection:
            self.worker = self.Worker(connection)
            self.worker.run()
        log.info('Mitigation Stopped..')


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection
            self.flag = False
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None

            # EXCHANGES
            self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
            self.mitigation_exchange = Exchange('mitigation', type='direct', durable=False, delivery_mode=1)
            self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=3,
                    consumer_arguments={'x-priority': 3})
            self.mitigate_queue = Queue(uuid(), exchange=self.mitigation_exchange, routing_key='mitigate', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.mitigate_start_queue = Queue(uuid(), exchange=self.mitigation_exchange, routing_key='mit_start', durable=False, exclusive=True, max_priority=2,
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
                        ),
                    Consumer(
                        queues=[self.mitigate_queue],
                        on_message=self.handle_mitigation_request,
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


        def handle_mitigation_request(self, message):
            hijack_event = message.payload
            prefix_node = self.prefix_tree.search_best(
                        hijack_event.prefix)
            if prefix_node is not None:
                mitigation_action = prefix_node.data['mitigation']
                if mitigation_action == 'manual':
                    log.info('Starting manual mitigation of hijack {}'.format(hijack_event))
                else:
                    log.info('Starting custom mitigation of hijack {}'.format(hijack_event))
                    hijack_event_str = json.dumps(hijack_event.to_dict())
                    subprocess.Popen([mitigation_action, '-i', hijack_event_str])
                # do something
                mit_started = {'key': message.payload['key'], 'time': time.time()}
                self.producer.publish(
                        mit_started,
                        exchange=self.mitigation_start_queue.exchange,
                        routing_key=self.mitigation_start_queue.routing_key,
                        priority=2
                )
            else:
                log.warn('No rule for hijack {}'.format(hijack_event))


