import radix
from webapp import app
from webapp.data.models import Hijack, db
import _thread
from multiprocessing import Queue
import subprocess
from sqlalchemy import and_, exc
import traceback
import time
import json


class Mitigation():

    def __init__(self, confparser):
        self.confparser = confparser
        self.hijack_queue = Queue()
        self.prefix_tree = radix.Radix()
        self.flag = False

    def init_mitigation(self):
        configs = self.confparser.get_obj()
        for config in configs:
            for prefix in configs[config]['prefixes']:
                node = self.prefix_tree.add(str(prefix))
                node.data['mitigation'] = configs[config]['mitigation']

    def start(self):
        if not self.flag:
            self.flag = True
            _thread.start_new_thread(self.parse_queue, ())

    def stop(self):
        if self.flag:
            self.flag = False
            self.hijack_queue.put(None)

    def parse_queue(self):
        with app.app_context():
            print('[+] Mitigation Mechanism Started...')
            self.init_mitigation()

            to_mitigate_events = Hijack.query.filter_by(to_mitigate=True).all()

            for hijack_event in to_mitigate_events:
                try:
                    if hijack_event is None:
                        continue

                    hijack_event.mitigation_started = time.time()
                    prefix_node = self.prefix_tree.search_best(
                        hijack_event.prefix)
                    if prefix_node is not None:
                        mitigation_action = prefix_node.data['mitigation']
                        if mitigation_action == 'manual':
                            print("[+] Starting manual mitigation of Hijack {}".format(hijack_event.id))
                        else:
                            print("[+] Starting custom mitigation of Hijack {}".format(hijack_event.id))
                            hijack_event_str = json.dumps(hijack_event.to_dict())
                            subprocess.Popen([mitigation_action, '-i', hijack_event_str])
                    hijack_event.to_mitigate = False

                    db.session.commit()
                    db.session.expunge(hijack_event)
                except Exception as e:
                    traceback.print_exc()

            while self.flag:
                try:
                    hijack_id = self.hijack_queue.get()
                    if hijack_id is None:
                        continue

                    hijack_event = Hijack.query.filter(
                                        Hijack.id.like(hijack_id)
                                ).first()

                    try:
                        db.session.add(hijack_event)
                    except exc.InvalidRequestError:
                        db.session.rollback()

                    hijack_event.mitigation_started = time.time()
                    prefix_node = self.prefix_tree.search_best(
                        hijack_event.prefix)
                    if prefix_node is not None:
                        mitigation_action = prefix_node.data['mitigation']
                        if mitigation_action == 'manual':
                            print("[+] Starting manual mitigation of Hijack {}".format(hijack_event.id))
                        else:
                            print("[+] Starting custom mitigation of Hijack {}".format(hijack_event.id))
                            hijack_event_str = json.dumps(hijack_event.to_dict())
                            subprocess.Popen([mitigation_action, '-i', hijack_event_str])
                    hijack_event.to_mitigate = False

                    db.session.commit()
                    db.session.expunge(hijack_event)
                except Exception as e:
                    traceback.print_exc()
            print('[+] Mitigation Mechanism Stopped...')
