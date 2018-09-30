from ipaddress import ip_network as str2ip
import os
import sys
from yaml import load as yload
from utils import flatten, get_logger, ArtemisError, RABBITMQ_HOST
from utils.service import Service
from socketIO_client_nexus import SocketIO
from kombu import Connection, Queue, Exchange, uuid
from kombu.mixins import ConsumerProducerMixin
import time
import logging


log = logging.getLogger('artemis_logger')

class Configuration(Service):


    def run_worker(self):
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except:
            log.exception('exception')
        finally:
            log.info('stopped')


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

            with open(self.file, 'r') as f:
                raw = f.read()
                self.data, _flag, _error = self.parse(raw, yaml=True)

            # EXCHANGES
            self.config_exchange = Exchange('config', type='direct', channel=connection, durable=False, delivery_mode=1)
            self.config_exchange.declare()

            # QUEUES
            self.config_modify_queue = Queue('config-modify-queue', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.config_request_queue = Queue('config-request-queue', durable=False, max_priority=2,
                    consumer_arguments={'x-priority': 2})

            self.parse_rrcs()
            log.info('started')


        def get_consumers(self, Consumer, channel):
            return [
                    Consumer(
                        queues=[self.config_modify_queue],
                        on_message=self.handle_config_modify,
                        prefetch_count=1,
                        no_ack=True,
                        accept=['yaml']
                        ),
                    Consumer(
                        queues=[self.config_request_queue],
                        on_message=self.handle_config_request,
                        prefetch_count=1,
                        no_ack=True
                        )
                    ]


        def handle_config_modify(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            raw = message.payload
            if 'yaml' in message.content_type:
                from io import StringIO
                stream = StringIO(''.join(raw))
                data, _flag, _error = self.parse(stream, yaml=True)
            else:
                data, _flag, _error = self.parse(raw)
            if _flag:
                log.debug('accepted new configuration')
                self.data = data
                self._update_local_config_file()
                self.producer.publish(
                    self.data,
                    exchange = self.config_exchange,
                    routing_key = 'notify',
                    serializer = 'json',
                    retry = True,
                    priority = 2
                )

                self.producer.publish(
                    {
                        'status': 'accepted',
                        'config:': self.data
                    },
                    exchange='',
                    routing_key = message.properties['reply_to'],
                    correlation_id = message.properties['correlation_id'],
                    serializer = 'json',
                    retry = True,
                    priority = 2
                )
            else:
                log.debug('rejected new configuration')
                self.producer.publish(
                    {
                        'status': 'rejected',
                        'reason': _error
                    },
                    exchange='',
                    routing_key = message.properties['reply_to'],
                    correlation_id = message.properties['correlation_id'],
                    serializer = 'json',
                    retry = True,
                    priority = 2
                )

        def handle_config_request(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            self.producer.publish(
                self.data,
                exchange='',
                routing_key = message.properties['reply_to'],
                correlation_id = message.properties['correlation_id'],
                serializer = 'json',
                retry = True,
                priority = 2
            )


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


        def parse(self, raw, yaml=False):
            try:
                if yaml:
                    data = yload(raw)
                else:
                    data = raw
                data = self.check(data)
                data['timestamp'] = time.time()
                if isinstance(raw, str):
                    data['raw_config'] = raw
                else:
                    data['raw_config'] = raw.getvalue()
                return data, True, None
            except Exception as e:
                log.exception('exception')
                return {'timestamp': time.time()}, False, str(e)


        def check(self, data):
            for section in data:
                if section not in self.sections:
                    raise ArtemisError('invalid-section', section)

            data['prefixes'] = {k:flatten(v) for k, v in data['prefixes'].items()}
            for prefix_group, prefixes in data['prefixes'].items():
                for prefix in prefixes:
                    try:
                        str2ip(prefix)
                    except:
                        raise ArtemisError('invalid-prefix', prefix)

            for rule in data['rules']:
                for field in rule:
                    if field not in self.supported_fields:
                        log.warning('unsupported field found {} in {}'.format(field, rule))
                rule['prefixes'] = flatten(rule['prefixes'])
                for prefix in rule['prefixes']:
                    try:
                        str2ip(prefix)
                    except:
                        raise ArtemisError('invalid-prefix', prefix)
                rule['origin_asns'] = flatten(rule.get('origin_asns', []))
                rule['neighbors'] = flatten(rule.get('neighbors', []))
                rule['mitigation'] = flatten(rule.get('mitigation', 'manual'))
                for asn in (rule['origin_asns'] + rule['neighbors']):
                    if not isinstance(asn, int):
                        raise ArtemisError('invalid-asn', asn)


            for key, info in data['monitors'].items():
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

            data['asns'] = {k:flatten(v) for k, v in data['asns'].items()}
            for name, asns in data['asns'].items():
                for asn in asns:
                    if not isinstance(asn, int):
                        raise ArtemisError('invalid-asn', asn)
            return data

        def _update_local_config_file(self):
            with open(self.file, 'w') as f:
                f.write(self.data['raw_config'])
