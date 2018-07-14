import radix
from webapp import app
from webapp.data.models import Hijack, Monitor, db
import _thread
from multiprocessing import Queue
from sqlalchemy import and_, exc, desc
import traceback


class Detection():

    def __init__(self, confparser):
        self.confparser = confparser
        self.monitor_queue = Queue()
        self.prefix_tree = radix.Radix()
        self.flag = False

    def init_detection(self):
        configs = self.confparser.get_obj()
        for config in configs:
            for prefix in configs[config]['prefixes']:
                node = self.prefix_tree.add(str(prefix))
                node.data['origin_asns'] = configs[config]['origin_asns']
                node.data['neighbors'] = configs[config]['neighbors']

    def start(self):
        if not self.flag:
            self.flag = True
            _thread.start_new_thread(self.parse_queue, ())

    def stop(self):
        if self.flag:
            self.flag = False
            self.monitor_queue.put(None)

    def parse_queue(self):
        with app.app_context():
            print('[+] Detection Mechanism Started..')
            self.init_detection()

            unhandled_events = Monitor.query.filter_by(handled=False).all()

            for monitor_event in unhandled_events:
                try:
                    if monitor_event is None:
                        continue

                    # ignore withdrawals for now
                    if monitor_event.type == 'W':
                        monitor_event.handled = True
                        db.session.commit()
                        continue

                    if not self.detect_origin_hijack(monitor_event):
                        if not self.detect_type_1_hijack(monitor_event):
                            monitor_event.handled = True
                            db.session.commit()
                            db.session.expunge(monitor_event)
                except Exception as e:
                    traceback.print_exc()

            while self.flag:
                try:
                    monitor_event = self.monitor_queue.get()
                    if monitor_event is None:
                        continue

                    try:
                        db.session.add(monitor_event)
                    except exc.InvalidRequestError:
                        db.session.rollback()

                    # ignore withdrawals for now
                    if monitor_event.type == 'W':
                        monitor_event.handled = True
                        db.session.commit()
                        continue

                    if not self.detect_origin_hijack(monitor_event):
                        if not self.detect_type_1_hijack(monitor_event):
                            monitor_event.handled = True
                            db.session.commit()
                            db.session.expunge(monitor_event)
                except Exception as e:
                    traceback.print_exc()
            print('[+] Detection Mechanism Stopped..')


    def detect_origin_hijack(self, monitor_event):
        try:
            if len(monitor_event.as_path) > 0:
                origin_asn = int(monitor_event.origin_as)
                prefix_node = self.prefix_tree.search_best(
                    monitor_event.prefix)
                if prefix_node is not None:
                    if origin_asn not in prefix_node.data['origin_asns']:
                        # Trigger hijack
                        hijack_event = Hijack.query.filter(
                            and_(
                                Hijack.type.like('0'),
                                Hijack.prefix.like(monitor_event.prefix),
                                Hijack.hijack_as.like(monitor_event.origin_as)
                            )
                        ).order_by(desc(Hijack.id)).first()

                        if hijack_event is None or hijack_event.time_ended is not None:
                            hijack = Hijack(monitor_event, origin_asn, 0)
                            db.session.add(hijack)
                            db.session.commit()
                            hijack_id = hijack.id
                            print('[DETECTION] NEW TYPE 0 HIJACK!\n{}'.format(hijack))
                        else:
                            if monitor_event.timestamp < hijack_event.time_started:
                                hijack_event.time_started = monitor_event.timestamp

                            if monitor_event.timestamp > hijack_event.time_last:
                                hijack_event.time_last = monitor_event.timestamp

                            hijack_monitors = Monitor.query.filter(
                                Monitor.hijack_id.like(hijack_event.id)
                            ).all()

                            peers_seen = set()
                            inf_asns = set()

                            for monitor in hijack_monitors:
                                peers_seen.add(monitor.peer_as)
                                inf_asns.update(
                                    set(monitor.as_path.split(' ')[:-1]))

                            peers_seen.add(monitor_event.peer_as)
                            inf_asns.update(
                                set(monitor_event.as_path.split(' ')[:-1]))
                            hijack_event.num_peers_seen = len(peers_seen)
                            hijack_event.num_asns_inf = len(inf_asns)
                            hijack_id = hijack_event.id

                        # Update monitor with new Hijack ID and register possible Hijack event changes
                        monitor_event.hijack_id = hijack_id
                        monitor_event.handled = True
                        db.session.commit()
                        db.session.expunge(monitor_event)

                        return True
            return False
        except Exception as e:
            traceback.print_exc()

    def detect_type_1_hijack(self, monitor_event):
        def remove_prepending(seq):
            last_add = None
            new_seq = []
            for x in seq:
                if last_add != x:
                    last_add = x
                    new_seq.append(x)

            if len(set(seq)) != len(new_seq):
                raise Exception('Routing Loop: {}'.format(seq))
            return new_seq

        try:
            if len(monitor_event.as_path) > 1:
                first_neighbor_asn = int(remove_prepending(monitor_event.as_path.split(' '))[-2])
                prefix_node = self.prefix_tree.search_best(
                    monitor_event.prefix)
                if prefix_node is not None:
                    if first_neighbor_asn not in prefix_node.data['neighbors']:
                        # Trigger hijack
                        hijack_event = Hijack.query.filter(
                            and_(
                                Hijack.type.like('1'),
                                Hijack.prefix.like(monitor_event.prefix),
                                Hijack.hijack_as.like(first_neighbor_asn)
                            )
                        ).order_by(desc(Hijack.id)).first()

                        if hijack_event is None or hijack_event.time_ended is not None:
                            hijack = Hijack(
                                monitor_event, first_neighbor_asn, 1)
                            db.session.add(hijack)
                            db.session.commit()
                            hijack_id = hijack.id
                            print('[DETECTION] NEW TYPE 1 HIJACK!\n{}'.format(hijack))
                        else:
                            if monitor_event.timestamp < hijack_event.time_started:
                                hijack_event.time_started = monitor_event.timestamp

                            if monitor_event.timestamp > hijack_event.time_last:
                                hijack_event.time_last = monitor_event.timestamp

                            hijack_monitors = Monitor.query.filter(
                                Monitor.hijack_id.like(hijack_event.id)
                            ).all()

                            peers_seen = set()
                            inf_asns = set()

                            for monitor in hijack_monitors:
                                peers_seen.add(monitor.peer_as)
                                inf_asns.update(
                                    set(monitor.as_path.split(' ')[:-2]))

                            peers_seen.add(monitor_event.peer_as)
                            inf_asns.update(
                                set(monitor_event.as_path.split(' ')[:-2]))
                            hijack_event.num_peers_seen = len(peers_seen)
                            hijack_event.num_asns_inf = len(inf_asns)
                            hijack_id = hijack_event.id

                        # Update monitor with new Hijack ID and register possible Hijack event changes
                        monitor_event.hijack_id = hijack_id
                        monitor_event.handled = True
                        db.session.commit()
                        db.session.expunge(monitor_event)

                        return True
            return False
        except Exception as e:
            traceback.print_exc()
