from ipaddress import ip_network as str2ip
import os
import sys
from yaml import load as yload
from utils import flatten, log, ArtemisError
from socketIO_client_nexus import SocketIO
from multiprocessing import Process
from kombu import Connection, Queue, Exchange
from kombu.mixins import ConsumerProducerMixin
import signal
import time
from setproctitle import setproctitle
import traceback

class Configuration(Process):


    def __init__(self):
        super().__init__()
        self.worker = None
        self.stopping = False


    def run(self):
        setproctitle(self.name)
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        try:
            with Connection('amqp://guest:guest@localhost:5672//') as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            traceback.print_exc()
        log.info('Configuration Stopped..')
        self.stopping = True


    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True
            while(self.stopping):
                time.sleep(1)


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection

            self.file = 'configs/config.yaml'
            self.sections = {'prefixes', 'asns', 'monitors', 'rules'}
            self.supported_fields = {'prefixes',
                                    'origin_asns', 'neighbors', 'mitigation'}
            self.supported_monitors = {
                'riperis', 'exabgp', 'bgpstreamhist', 'bgpstreamlive'}
            self.available_ris = set()
            self.available_bgpstreamlive = {'routeviews', 'ris'}
            self.flag = False

            with open(self.file, 'r') as f:
                self.raw = f.read()


            # EXCHANGES
            self.control_exchange = Exchange('control', 'direct', durable=False, delivery_mode=1)
            self.config_modify_exchange = Exchange('configuration', 'direct', durable=False, delivery_mode=1)


            # QUEUES
            self.control_queue = Queue('control_queue', exchange=self.control_exchange, routing_key='configuration', durable=False)
            self.config_modify_queue = Queue('config_modify_queue', exchange=self.config_modify_exchange, routing_key='modification', durable=False)
            self.config_request_queue = Queue('config_request_queue', durable=False)

            self.parse_rrcs()
            self.parse()
            self.flag = True
            log.info('Configuration Started..')


        def get_consumers(self, Consumer, channel):
            return [Consumer(
                queues=[self.config_modify_queue],
                on_message=self.handle_config_modify,
                prefetch_count=1,
                no_ack=True
            ), Consumer(
                queues=[self.control_queue],
                on_message=self.handle_control,
                prefetch_count=1,
                no_ack=True
            ), Consumer(
                queues=[self.config_request_queue],
                on_message=self.handle_config_request,
                prefetch_count=1,
            )]


        def handle_config_modify(self, message):
            print(' [x] Configuration - Config Modify {}'.format(message.payload))
            self.parse()


        def handle_control(self, message):
            print(' [x] Configuration - Handle Control {}'.format(message.payload))
            getattr(self, message.payload)()


        def handle_config_request(self, message):
            log.info(' [x] Configuration - Received configuration request')
            self.producer.publish(
                self.data,
                exchange='',
                routing_key = message.properties['reply_to'],
                correlation_id = message.properties['correlation_id'],
                serializer = 'json',
                retry = True
            )
            message.ack()


        def parse_rrcs(self):
            try:
                socket_io = SocketIO('http://stream-dev.ris.ripe.net/stream', wait_for_connection=False)
                def on_msg(msg):
                    self.available_ris = set(msg)
                    socket_io.disconnect()
                socket_io.on('ris_rrc_list', on_msg)
                socket_io.wait(seconds=3)
            except Exception:
                log.warning('RIPE RIS server is down. Try again later..')


        def parse(self):
            self.data = yload(self.raw)
            self.check()


        def check(self):
            for section in self.data:
                if section not in self.sections:
                    raise ArtemisError('invalid-section', section)

            self.data['prefixes'] = {k:flatten(v) for k, v in self.data['prefixes'].items()}
            for prefix_group, prefixes in self.data['prefixes'].items():
                for prefix in prefixes:
                    try:
                        str2ip(prefix)
                    except:
                        raise ArtemisError('invalid-prefix', prefix)

            for rule in self.data['rules']:
                for field in rule:
                    if field not in self.supported_fields:
                        log.warning('Unsupported field found {} in {}'.format(field, rule))
                rule['prefixes'] = flatten(rule['prefixes'])
                for prefix in rule['prefixes']:
                    try:
                        str2ip(prefix)
                    except:
                        raise ArtemisError('invalid-prefix', prefix)
                rule['origin_asns'] = flatten(rule.get('origin_asns', []))
                rule['neighbors'] = flatten(rule.get('neighbors', []))
                for asn in (rule['origin_asns'] + rule['neighbors']):
                    if not isinstance(asn, int):
                        raise ArtemisError('invalid-asn', asn)


            for key, info in self.data['monitors'].items():
                if key not in self.supported_monitors:
                    raise ArtemisError('invalid-monitor', key)
                elif key == 'riperis':
                    for unavailable in set(info).difference(self.available_ris):
                        log.warning('unavailable monitor {}'.format(unavailable))
                elif key == 'bgpstreamlive':
                    if len(info) == 0 or not set(info).issubset(self.available_bgpstreamlive):
                        raise ArtemisError('invalid-bgpstreamlive-project', info)
                elif key == 'exabgp':
                    for entry in info:
                        if 'ip' not in entry and 'port' not in entry:
                            raise ArtemisError('invalid-exabgp-info', entry)
                        try:
                            str2ip(entry['ip'])
                        except:
                            raise ArtemisError('invalid-exabgp-ip', entry['ip'])
                        if not isinstance(entry['port'], int):
                            raise ArtemisError('invalid-exabgp-port', entry['port'])

            self.data['asns'] = {k:flatten(v) for k, v in self.data['asns'].items()}
            for name, asns in self.data['asns'].items():
                for asn in asns:
                    if not isinstance(asn, int):
                        raise ArtemisError('invalid-asn', asn)


