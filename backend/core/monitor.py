import radix
from subprocess import Popen
from utils import exception_handler, RABBITMQ_HOST, get_logger
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import signal


log = get_logger()


class Monitor():

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
            if self.worker is not None:
                self.worker.stop()
            log.info('stopped')

    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):

        def __init__(self, connection):
            self.connection = connection
            self.timestamp = -1
            self.prefix_tree = None
            self.process_ids = []
            self.rules = None
            self.prefixes = set()
            self.monitors = None
            self.flag = True

            # EXCHANGES
            self.config_exchange = Exchange(
                'config', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.config_queue = Queue(
                'monitor-config-notify', exchange=self.config_exchange, routing_key='notify', durable=False, auto_delete=True, max_priority=2,
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
                self.monitors = raw.get('monitors', {})
                self.start_monitors()

        def start_monitors(self):
            for proc_id in self.process_ids:
                try:
                    proc_id[1].terminate()
                except ProcessLookupError:
                    log.exception('process terminate')
            self.process_ids.clear()
            self.prefixes.clear()

            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                try:
                    for prefix in rule['prefixes']:
                        node = self.prefix_tree.add(prefix)
                        node.data['origin_asns'] = rule['origin_asns']
                        node.data['neighbors'] = rule['neighbors']
                        node.data['mitigation'] = rule['mitigation']
                except Exception as e:
                    log.error('Exception', exc_info=True)

            # only keep super prefixes for monitors
            for prefix in self.prefix_tree.prefixes():
                self.prefixes.add(self.prefix_tree.search_worst(prefix).prefix)

            self.init_ris_instances()
            self.init_exabgp_instances()
            self.init_bgpstreamhist_instance()
            self.init_bgpstreamlive_instance()
            self.init_betabmp_instance()

        def stop(self):
            if self.flag:
                for proc_id in self.process_ids:
                    try:
                        proc_id[1].terminate()
                    except ProcessLookupError:
                        log.exception('process terminate')
                self.flag = False
                self.rules = None
                self.monitors = None

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
                          queues=[callback_queue], no_ack=True):
                while self.rules is None and self.monitors is None:
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
                    self.monitors = raw.get('monitors', {})
                    self.start_monitors()

        @exception_handler(log)
        def init_ris_instances(self):
            log.debug(
                'starting {} for {}'.format(
                    self.monitors.get(
                        'riperis',
                        []),
                    self.prefixes))
            for ris_monitor in self.monitors.get('riperis', []):
                for prefix in self.prefixes:
                    p = Popen(['/usr/local/bin/python3', 'taps/ripe_ris.py',
                               '--prefix', prefix, '--host', ris_monitor], shell=False)
                    self.process_ids.append(
                        ('RIPEris {} {}'.format(ris_monitor, prefix), p))

        @exception_handler(log)
        def init_exabgp_instances(self):
            log.debug(
                'starting {} for {}'.format(
                    self.monitors.get(
                        'exabgp',
                        []),
                    self.prefixes))
            for exabgp_monitor in self.monitors.get('exabgp', []):
                exabgp_monitor_str = '{}:{}'.format(
                    exabgp_monitor['ip'], exabgp_monitor['port'])
                p = Popen(['/usr/local/bin/python3', 'taps/exabgp_client.py',
                           '--prefix', ','.join(self.prefixes), '--host', exabgp_monitor_str], shell=False)
                self.process_ids.append(
                    ('ExaBGP {} {}'.format(
                        exabgp_monitor_str, self.prefixes), p))

        @exception_handler(log)
        def init_bgpstreamhist_instance(self):
            if 'bgpstreamhist' in self.monitors:
                log.debug(
                    'starting {} for {}'.format(
                        self.monitors['bgpstreamhist'],
                        self.prefixes))
                bgpstreamhist_dir = self.monitors['bgpstreamhist']
                p = Popen(['/usr/local/bin/python3', 'taps/bgpstreamhist.py',
                           '--prefix', ','.join(self.prefixes), '--dir', bgpstreamhist_dir], shell=False)
                self.process_ids.append(
                    ('BGPStreamHist {} {}'.format(
                        bgpstreamhist_dir, self.prefixes), p))

        @exception_handler(log)
        def init_bgpstreamlive_instance(self):
            if 'bgpstreamlive' in self.monitors:
                log.debug(
                    'starting {} for {}'.format(
                        self.monitors['bgpstreamlive'],
                        self.prefixes))
                bgpstream_projects = ','.join(self.monitors['bgpstreamlive'])
                p = Popen(['/usr/local/bin/python3', 'taps/bgpstreamlive.py',
                           '--prefix', ','.join(self.prefixes), '--mon_projects', bgpstream_projects], shell=False)
                self.process_ids.append(
                    ('BGPStreamLive {} {}'.format(
                        bgpstream_projects, self.prefixes), p))

        @exception_handler(log)
        def init_betabmp_instance(self):
            if 'betabmp' in self.monitors:
                log.debug(
                    'starting {} for {}'.format(
                        self.monitors['betabmp'],
                        self.prefixes))
                p = Popen(['/usr/local/bin/python3', 'taps/betabmp.py',
                           '--prefix', ','.join(self.prefixes)], shell=False)
                self.process_ids.append(
                    ('Beta BMP {}'.format(
                        self.prefixes), p))


def run():
    service = Monitor()
    service.run()


if __name__ == '__main__':
    run()
