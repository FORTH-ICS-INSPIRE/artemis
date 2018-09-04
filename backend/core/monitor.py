import sys
import os
import radix
from subprocess import Popen
from utils import exception_handler, log, RABBITMQ_HOST
from service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
import traceback


class Monitor(Service):


    def __init__(self, name='Monitor', pid_dir='/tmp'):
        super().__init__(name=name, pid_dir=pid_dir)
        self.worker = None
        self.stopping = False


    def run(self):
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
        log.info('Monitors Stopped..')
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
            self.prefix_tree = None
            self.process_ids = []
            self.rules = None
            self.prefixes = set()
            self.monitors = None


            # EXCHANGES
            self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})

            self.config_request_rpc()
            self.flag = True
            log.info('Monitor Started..')


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
            log.info(' [x] Monitor - Config Notify')
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.monitors = raw.get('monitors', {})
                self.start_monitors()


        def start_monitors(self):
            for proc_id in self.process_ids:
                proc_id[1].terminate()
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


        def stop(self):
            if self.flag:
                for proc_id in self.process_ids:
                    proc_id[1].terminate()
                self.flag = False
                self.rules = None
                self.monitors = None


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
                        queues=[callback_queue], no_ack=True):
                while self.rules is None and self.monitors is None:
                    self.connection.drain_events()


        def handle_config_request_reply(self, message):
            log.info(' [x] Monitor - Received Configuration')
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                if raw['timestamp'] > self.timestamp:
                    self.timestamp = raw['timestamp']
                    self.rules = raw.get('rules', [])
                    self.monitors = raw.get('monitors', {})
                    self.start_monitors()


        @exception_handler
        def init_ris_instances(self):
            log.debug('Starting {} for {}'.format(self.monitors.get('riperis', []), self.prefixes))
            for ris_monitor in self.monitors.get('riperis', []):
                for prefix in self.prefixes:
                        p = Popen(['python3', 'taps/ripe_ris.py',
                                    '--prefix', prefix, '--host', ris_monitor])
                        self.process_ids.append(('RIPEris {} {}'.format(ris_monitor, prefix), p))


        @exception_handler
        def init_exabgp_instances(self):
            log.debug('Starting {} for {}'.format(self.monitors.get('exabgp', []), self.prefixes))
            for exabgp_monitor in self.monitors.get('exabgp', []):
                exabgp_monitor_str = '{}:{}'.format(exabgp_monitor['ip'] ,exabgp_monitor['port'])
                p = Popen(['python3', 'taps/exabgp_client.py',
                    '--prefix', ','.join(self.prefixes), '--host', exabgp_monitor_str])
                self.process_ids.append(('ExaBGP {} {}'.format(exabgp_monitor_str, self.prefixes), p))


        @exception_handler
        def init_bgpstreamhist_instance(self):
            if 'bgpstreamhist' in self.monitors:
                log.debug('Starting {} for {}'.format(self.monitors['bgpstreamhist'], self.prefixes))
                bgpstreamhist_dir = self.monitors['bgpstreamhist']
                p = Popen(['python3', 'taps/bgpstreamhist.py',
                        '--prefix', ','.join(self.prefixes), '--dir', bgpstreamhist_dir])
                self.process_ids.append(('BGPStreamHist {} {}'.format(bgpstreamhist_dir, self.prefixes), p))


        @exception_handler
        def init_bgpstreamlive_instance(self):
            if 'bgpstreamlive' in self.monitors:
                log.debug('Starting {} for {}'.format(self.monitors['bgpstreamlive'], self.prefixes))
                bgpstream_projects = ','.join(self.monitors['bgpstreamlive'])
                p = Popen(['python3', 'taps/bgpstreamlive.py',
                        '--prefix', ','.join(self.prefixes), '--mon_projects', bgpstream_projects])
                self.process_ids.append(('BGPStreamLive {} {}'.format(bgpstream_projects, self.prefixes), p))

