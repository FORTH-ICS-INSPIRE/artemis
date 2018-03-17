import os
import sys
import radix
import signal
from core.mitigation import Mitigation
from webapp.models import Hijack
from multiprocessing import Process


class Detection():

    def __init__(self, db, confparser, monitor_queue):
        self.confparser = confparser
        self.monitor_queue = monitor_queue
        self.prefix_tree = radix.Radix()
        self.db = db
        self.flag = False
        self.detection_ = None

    def init_detection(self):
        configs = self.confparser.get_obj()
        for config in configs:
            for prefix in configs[config]['prefixes']:
                node = self.prefix_tree.add(str(prefix))
                node.data['origin_asns'] = configs[config]['origin_asns']
                node.data['neighbors'] = configs[config]['neighbors']
                node.data['mitigation'] = configs[config]['mitigation']

    def start(self):
        if not self.flag:
            print('Starting Detection mechanism...')
            self.flag = True
            self.detection_ = Process(target=self.parse_queue, args=())
            self.detection_.start()

    def stop(self):
        if self.flag:
            print('Stopping Detection mechanism...')
            self.detection_.terminate()
            self.flag = False

    def parse_queue(self):
        self.init_detection()
        while self.flag:
            try:
                parsed_log = self.monitor_queue.get()
                if(not self.detect_origin_hijack(parsed_log)):
                    if(not self.detect_type_1_hijack(parsed_log)):
                        pass
            except Exception as e:
                print(
                    '[DETECTION] Error on raw log queue parsing.. {}'
                    .format(e)
                )

    def detect_origin_hijack(self, bgp_msg):
        try:
            if len(bgp_msg['as_path']) > 0:
                origin_asn = int(bgp_msg['as_path'][-1])
                prefix_node = self.prefix_tree.search_best(bgp_msg['prefix'])
                if prefix_node is not None:
                    if origin_asn not in prefix_node.data['origin_asns']:
                        # Trigger hijack
                        print('[DETECTION] HIJACK TYPE 0 detected!')

                        self.db.session.add(Hijack(bgp_msg, 0))
                        self.db.session.commit()

                        # if len(prefix_node.data['mitigation']) > 0:
                        #     mit = Mitigation(
                        #         prefix_node,
                        #         bgp_msg,
                        #         self.local_mitigation,
                        #         self.moas_mitigation)
                        return True
            return False
        except Exception as e:
            print(
                '[DETECTION] Error on detect origin hijack.. {}:{}'
                .format(e, bgp_msg)
            )

    def detect_type_1_hijack(self, bgp_msg):
        try:
            if len(bgp_msg['as_path']) > 1:
                first_neighbor_asn = int(bgp_msg['as_path'][-2])
                prefix_node = self.prefix_tree.search_best(bgp_msg['prefix'])
                if prefix_node is not None:
                    if first_neighbor_asn not in prefix_node.data['neighbors']:
                        # Trigger hijack
                        print('[DETECTION] HIJACK TYPE 1 detected!')

                        self.db.session.add(Hijack(bgp_msg, 1))
                        self.db.session.commit()

                        # if len(prefix_node.data['mitigation']) > 0:
                        #     mit = Mitigation(
                        #         prefix_node,
                        #         bgp_msg,
                        #         self.local_mitigation,
                        #         self.moas_mitigation)
                        return True
            return False
        except Exception as e:
            print(
                '[DETECTION] Error on detect 1 hop neighbor hijack.. {}:{}'
                .format(e, bgp_msg)
            )
