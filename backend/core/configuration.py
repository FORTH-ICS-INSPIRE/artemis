from ipaddress import ip_network as str2ip
from yaml import load as yload
from utils import flatten, ArtemisError, RABBITMQ_HOST, get_logger
import utils.conf_lib as clib
from socketIO_client_nexus import SocketIO
from kombu import Connection, Queue, Exchange, Consumer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
import json
import copy
from typing import Union, Optional, Dict, TextIO, Text, List, NoReturn
from io import StringIO


log = get_logger()


class Configuration():

    """
    Configuration Service.
    """

    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self) -> NoReturn:
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

        """
        RabbitMQ Consumer/Producer for this Service.
        """

        def __init__(self, connection: Connection) -> NoReturn:
            self.connection = connection
            self.file = '/etc/artemis/config.yaml'
            self.sections = {'prefixes', 'asns', 'monitors', 'rules'}
            self.supported_fields = {
                'prefixes',
                'origin_asns',
                'neighbors',
                'mitigation'}
            self.supported_monitors = {
                'riperis', 'exabgp', 'bgpstreamhist', 'bgpstreamlive', 'betabmp'}
            self.available_ris = set()
            self.available_bgpstreamlive = {'routeviews', 'ris'}

            # reads and parses initial configuration file
            with open(self.file, 'r') as f:
                raw = f.read()
                self.data, _flag, _error = self.parse(raw, yaml=True)

            # EXCHANGES
            self.config_exchange = Exchange(
                'config',
                type='direct',
                channel=connection,
                durable=False,
                delivery_mode=1)
            self.config_exchange.declare()

            # QUEUES
            self.config_modify_queue = Queue(
                'config-modify-queue',
                durable=False,
                max_priority=4,
                consumer_arguments={
                    'x-priority': 4})
            self.config_request_queue = Queue(
                'config-request-queue',
                durable=False,
                max_priority=4,
                consumer_arguments={
                    'x-priority': 4})

            self.parse_rrcs()
            log.info('started')

        def get_consumers(self, Consumer: Consumer,
                          channel: Connection) -> List[Consumer]:
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

        def handle_config_modify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Modify messages that parses and checks if new configuration is correct.
            Replies back to the sender if the configuration is accepted or rejected and notifies all Subscribers if new configuration is used.
            """
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            raw_ = message.payload

            # Case received config from Frontend with comment
            comment = None
            if isinstance(raw_, dict) and 'comment' in raw_:
                comment = raw_['comment']
                del raw_['comment']
                raw = raw_['config']
            else:
                raw = raw_

            if 'yaml' in message.content_type:
                stream = StringIO(''.join(raw))
                data, _flag, _error = self.parse(stream, yaml=True)
            else:
                data, _flag, _error = self.parse(raw)

            # _flag is True or False depending if the new configuration was
            # accepted or not.
            if _flag:
                log.debug('accepted new configuration')
                # compare current with previous data excluding --obviously-- timestamps
                # TODO: change to sth better
                prev_data = copy.deepcopy(data)
                del prev_data['timestamp']
                new_data = copy.deepcopy(self.data)
                del new_data['timestamp']
                prev_data_str = json.dumps(prev_data, sort_keys=True)
                new_data_str = json.dumps(new_data, sort_keys=True)
                if prev_data_str != new_data_str:
                    self.data = data
                    self._update_local_config_file()
                    if comment is not None:
                        self.data['comment'] = comment

                    self.producer.publish(
                        self.data,
                        exchange=self.config_exchange,
                        routing_key='notify',
                        serializer='json',
                        retry=True,
                        priority=2
                    )
                    # Remove the comment to avoid marking config as different
                    if 'comment' in self.data:
                        del self.data['comment']

                # reply back to the sender with a configuration accepted
                # message.
                self.producer.publish(
                    {
                        'status': 'accepted',
                        'config:': self.data
                    },
                    exchange='',
                    routing_key=message.properties['reply_to'],
                    correlation_id=message.properties['correlation_id'],
                    serializer='json',
                    retry=True,
                    priority=4
                )
            else:
                log.debug('rejected new configuration')
                # replay back to the sender with a configuration rejected and
                # reason message.
                self.producer.publish(
                    {
                        'status': 'rejected',
                        'reason': _error
                    },
                    exchange='',
                    routing_key=message.properties['reply_to'],
                    correlation_id=message.properties['correlation_id'],
                    serializer='json',
                    retry=True,
                    priority=4
                )

        def handle_config_request(self, message: Dict) -> NoReturn:
            """
            Handles all config requests from other Services by replying back with the current configuration.
            """
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            self.producer.publish(
                self.data,
                exchange='',
                routing_key=message.properties['reply_to'],
                correlation_id=message.properties['correlation_id'],
                serializer='json',
                retry=True,
                priority=4
            )

        def parse_rrcs(self) -> NoReturn:
            """
            SocketIO connection to RIPE RIS to retrieve all active Route Collectors.
            """
            try:
                socket_io = SocketIO(
                    'http://stream-dev.ris.ripe.net/stream',
                    wait_for_connection=False)

                def on_msg(msg):
                    self.available_ris = set(msg)
                    socket_io.disconnect()

                socket_io.on('ris_rrc_list', on_msg)
                socket_io.wait(seconds=3)
            except Exception:
                log.warning('RIPE RIS server is down. Try again later..')

        def parse(self, raw: Union[Text, TextIO, StringIO],
                  yaml: Optional[bool]=False) -> Dict:
            """
            Parser for the configuration file or string. The format can either be a File, StringIO or String
            """
            try:
                if yaml:
                    data = yload(raw)
                else:
                    data = raw
                data = self.check(data)
                data['timestamp'] = time.time()
                # if raw is string we save it as-is else we get the value.
                if isinstance(raw, str):
                    data['raw_config'] = raw
                else:
                    data['raw_config'] = raw.getvalue()
                return data, True, None
            except Exception as e:
                log.exception('exception')
                return {'timestamp': time.time()}, False, str(e)

        def check(self, data: Text) -> Dict:
            """
            Checks if all sections and fields are defined correctly in the parsed configuration.
            Raises custom exceptions in case a field or section is misdefined.
            """
            for section in data:
                if section not in self.sections:
                    raise ArtemisError('invalid-section', section)

            data['prefixes'] = {k: flatten(v)
                                for k, v in data['prefixes'].items()}
            for prefix_group, prefixes in data['prefixes'].items():
                for prefix in prefixes:
                    try:
                        str2ip(prefix)
                    except Exception:
                        raise ArtemisError('invalid-prefix', prefix)

            for rule in data['rules']:
                for field in rule:
                    if field not in self.supported_fields:
                        log.warning(
                            'unsupported field found {} in {}'.format(
                                field, rule))
                rule['prefixes'] = flatten(rule['prefixes'])
                for prefix in rule['prefixes']:
                    try:
                        str2ip(prefix)
                    except Exception:
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
                    for unavailable in set(info).difference(
                            self.available_ris):
                        log.warning(
                            'unavailable monitor {}'.format(unavailable))
                elif key == 'bgpstreamlive':
                    if len(info) == 0 or not set(info).issubset(
                            self.available_bgpstreamlive):
                        raise ArtemisError(
                            'invalid-bgpstreamlive-project', info)
                elif key == 'exabgp':
                    for entry in info:
                        if 'ip' not in entry and 'port' not in entry:
                            raise ArtemisError('invalid-exabgp-info', entry)
                        if entry['ip'] != 'exabgp':
                            try:
                                str2ip(entry['ip'])
                            except Exception:
                                raise ArtemisError(
                                    'invalid-exabgp-ip', entry['ip'])
                        if not isinstance(entry['port'], int):
                            raise ArtemisError(
                                'invalid-exabgp-port', entry['port'])

            data['asns'] = {k: flatten(v) for k, v in data['asns'].items()}
            for name, asns in data['asns'].items():
                for asn in asns:
                    if not isinstance(asn, int):
                        raise ArtemisError('invalid-asn', asn)
            return data

        def _update_local_config_file(self) -> NoReturn:
            """
            Writes to the local configuration file the new running configuration.
            """
            with open(self.file, 'w') as f:
                f.write(self.data['raw_config'])


def run():
    service = Configuration()
    service.run()


if __name__ == '__main__':
    run()
