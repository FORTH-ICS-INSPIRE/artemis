import sys
import os
import radix
# from taps.bgpmon import BGPmon
from subprocess import Popen
from core import exception_handler, log


class Monitor():

    def __init__(self, confparser):
        self.prefix_tree = radix.Radix()
        self.process_ids = list()
        self.flag = False
        self.configs = confparser.get_obj()
        self.prefixes = set()
        self.monitors = confparser.get_monitors()

    def start(self):
        if not self.flag:
            for config in self.configs:
                try:
                    for prefix in self.configs[config]['prefixes']:
                        node = self.prefix_tree.add(str(prefix))
                        node.data['origin_asns'] = self.configs[
                            config]['origin_asns']
                        node.data['neighbors'] = self.configs[config]['neighbors']
                        node.data['mitigation'] = self.configs[
                            config]['mitigation']
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
            for proc_id in self.process_ids:
                proc_id[1].terminate()
            self.flag = False
            log.info('Monitors Stopped..')

    @exception_handler
    def init_ris_instances(self):
        log.debug('Starting {} for {}'.format(self.monitors.get('riperis', []), self.prefixes))
        for ris_monitor in self.monitors.get('riperis', []):
            for prefix in self.prefixes:
                    p = Popen(['nodejs', 'taps/ripe_ris.js',
                                '--prefix', prefix, '--host', ris_monitor])
                    self.process_ids.append(('RIPEris {} {}'.format(ris_monitor, prefix), p))

    # def init_bgpmon_instance(self, prefixes):
    #   try:
    #       if(len(self.confparser.get_monitors()['bgpmon']) == 1):
    #           p = Process(target=BGPmon, args=(self.prefix_tree, self.raw_log_queue, self.confparser.get_monitors()['bgpmon'][0]))
    #           p.start()
    #           self.process_ids.append(('BGPmon', p))
    #   except:
    #       print('Error on initializing of BGPmon.')

    @exception_handler
    def init_exabgp_instances(self):
        log.debug('Starting {} for {}'.format(self.monitors.get('exabgp', []), self.prefixes))
        for exabgp_monitor in self.monitors.get('exabgp', []):
            exabgp_monitor_str = '{}:{}'.format(exabgp_monitor[0] ,exabgp_monitor[1])
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
