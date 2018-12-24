import radix
import subprocess
from utils import RABBITMQ_HOST, get_logger
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import time
import json
import signal


log = get_logger()


class Mitigation():

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

    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None

            # EXCHANGES
            self.mitigation_exchange = Exchange(
                'mitigation',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.mitigation_exchange.declare()
            self.config_exchange = Exchange(
                'config', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.config_queue = Queue(
                'mitigation-config-notify', exchange=self.config_exchange, routing_key='notify', durable=False, auto_delete=True, max_priority=3,
                consumer_arguments={'x-priority': 3})
            self.mitigate_queue = Queue(
                'mitigation-mitigate', exchange=self.mitigation_exchange, routing_key='mitigate', durable=False, auto_delete=True, max_priority=2,
                consumer_arguments={'x-priority': 2})

            self.config_request_rpc()
            log.info('started')

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
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.init_mitigation()

        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(),
                                   durable=False,
                                   auto_delete=True,
                                   max_priority=4,
                                   consumer_arguments={
                'x-priority': 4})

            self.producer.publish(
                '',
                exchange='',
                routing_key='config-request-queue',
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        'config-request-queue',
                        durable=False,
                        max_priority=4,
                        consumer_arguments={
                            'x-priority': 4}),
                    callback_queue
                ],
                priority=4
            )
            with Consumer(self.connection,
                          on_message=self.handle_config_request_reply,
                          queues=[callback_queue],
                          no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()

        def handle_config_request_reply(self, message):
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
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
                hijack_event['prefix'])
            if prefix_node is not None:
                mitigation_action = prefix_node.data['mitigation'][0]
                if mitigation_action == 'manual':
                    log.info(
                        'starting manual mitigation of hijack {}'.format(hijack_event))
                else:
                    log.info(
                        'starting custom mitigation of hijack {}'.format(hijack_event))
                    hijack_event_str = json.dumps(hijack_event)
                    subprocess.Popen(
                        ' '.join([mitigation_action, '-i', hijack_event_str]), shell=False)
                # do something
                mit_started = {'key': hijack_event['key'], 'time': time.time()}
                self.producer.publish(
                    mit_started,
                    exchange=self.mitigation_exchange,
                    routing_key='mit-start',
                    priority=2
                )
            else:
                log.warn('no rule for hijack {}'.format(hijack_event))


def run():
    service = Mitigation()
    service.run()


if __name__ == '__main__':
    run()
