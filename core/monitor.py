import sys
import os
import radix
from subprocess import Popen
from utils import exception_handler, log, decorators
import uuid
import pika
import pickle
import threading


class Monitor(object):


    def __init__(self):
        self.prefix_tree = radix.Radix()
        self.process_ids = []
        self.flag = False
        self.rules = None
        self.prefixes = set()
        self.monitors = None
        self.handle_control_consumer = self.handle_control()


    def init_start(self):
        threading.Thread(target=self.handle_control_consumer.run, args=()).start()
        self.start()


    def final_stop(self):
        self.handle_control_consumer.stop()
        self.stop()


    def restart(self):
        self.stop()
        self.start()


    def start(self):
        if not self.flag:
            self.rpc_request_config()
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
            # self.init_bgpmon_instance()
            self.init_exabgp_instances()
            self.init_bgpstreamhist_instance()
            self.init_bgpstreamlive_instance()
            self.flag = True
            log.info('Monitors Started..')


    def stop(self):
        if self.flag:
            try:
                self.channel.stop_consuming()
            except:
                pass
            for proc_id in self.process_ids:
                proc_id[1].terminate()
            self.flag = False
            self.rules = None
            self.monitors = None
            log.info('Monitors Stopped..')


    def rpc_request_config(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self.channel = self.connection.channel()
        result = self.channel.queue_declare(exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(self.handle_config_request_reply, no_ack=True,
                                queue=self.callback_queue)
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(exchange='',
                                routing_key='rpc_config_queue',
                                properties=pika.BasicProperties(
                                        reply_to = self.callback_queue,
                                        correlation_id = self.corr_id,
                                        ),
                                body='')

        while self.rules is None and self.monitors is None:
            self.connection.process_data_events()


    def handle_config_request_reply(self, channel, method, header, body):
        log.info(' [x] Monitor - Received Configuration')
        if self.corr_id == header.correlation_id:
            raw = pickle.loads(body)
            self.rules = raw.get('rules', [])
            self.monitors = raw.get('monitors', [])


    @decorators.consumer_callback('control', 'direct', 'monitor')
    def handle_control(self, channel, method, header, body):
        msg = pickle.loads(body)
        print(' [x] Monitor - Handle Control {}'.format(msg))
        getattr(self, msg)()


    @exception_handler
    def init_ris_instances(self):
        log.debug('Starting {} for {}'.format(self.monitors.get('riperis', []), self.prefixes))
        for ris_monitor in self.monitors.get('riperis', []):
            for prefix in self.prefixes:
                    p = Popen(['nodejs', 'taps/ripe_ris.js',
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

