from ipaddress import ip_network as str2ip
import os
import sys
from yaml import load as yload
from utils import flatten, log, ArtemisError, decorators
from utils.mq import AsyncConnection
from socketIO_client_nexus import SocketIO
import pika
import pickle
import threading


class Configuration():


    def __init__(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self.channel = connection.channel()
        self.channel.queue_declare(queue='rpc_config_queue')
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(self.handle_config_request, queue='rpc_config_queue')

        self.file = 'configs/config.yaml'
        self.sections = {'prefixes', 'asns', 'monitors', 'rules'}
        self.supported_fields = {'prefixes',
                                 'origin_asns', 'neighbors', 'mitigation'}
        self.supported_monitors = {
            'riperis', 'exabgp', 'bgpstreamhist', 'bgpstreamlive'}
        self.available_ris = set()
        self.available_bgpstreamlive = {'routeviews', 'ris'}
        self.flag = False
        self.configuration_publisher = AsyncConnection(exchange='config_notify',
                exchange_type='direct',
                routing_key='notification',
                objtype='publisher')

        with open(self.file, 'r') as f:
            self.raw = f.read()

        self.handle_config_modify_consumer = self.handle_config_modify()
        self.handle_control_consumer = self.handle_control()


    def init_start(self):
        threading.Thread(target=self.handle_control_consumer.run, args=()).start()
        threading.Thread(target=self.configuration_publisher.run, args=()).start()
        self.start()


    def final_stop(self):
        self.handle_control_consumer.stop()
        self.configuration_publisher.stop()
        self.stop()


    def start(self):
        if not self.flag:
            self.flag = True
            threading.Thread(target=self.channel.start_consuming, args=()).start()
            threading.Thread(target=self.handle_config_modify_consumer.run, args=()).start()
            self.parse_rrcs()
            self.parse()
            log.info('Configuration Started..')


    def stop(self):
        if self.flag:
            self.channel.stop_consuming()
            self.handle_config_modify_consumer.stop()
            self.flag = False
            log.info('Configuration Stopped..')


    @decorators.consumer_callback('config_modify', 'direct', 'modification')
    def handle_config_modify(self, channel, method, header, body):
        self.raw = pickle.loads(body)
        print(' [x] Configuration - Config Modify {}'.format(msg))
        self.parse()
        self.configuration_publisher.publish_message(self.data)


    @decorators.consumer_callback('control', 'direct', 'configuration')
    def handle_control(self, channel, method, header, body):
        msg = pickle.loads(body)
        print(' [x] Configuration - Handle Control {}'.format(msg))
        getattr(self, msg)()


    def handle_config_request(self, channel, method, header, body):
        log.info(' [x] Configuration - Sending configuration')
        channel.basic_publish(exchange='',
                     routing_key=header.reply_to,
                     properties=pika.BasicProperties(correlation_id = \
                                                         header.correlation_id),
                     body=pickle.dumps(self.data))
        channel.basic_ack(delivery_tag = method.delivery_tag)


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


