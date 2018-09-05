import psycopg2
import radix
from utils import log, exception_handler, RABBITMQ_HOST
from multiprocessing import Process
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
from setproctitle import setproctitle
import traceback
import pickle
import json

class Postgresql_db(Process):


    def __init__(self):
        super().__init__()
        self.worker = None
        self.stopping = False

    def run(self):
        setproctitle(self.name)
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            traceback.print_exc()
        log.info('SQLite_db Stopped..')
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
            self.prefix_tree = None
            self.rules = None
            self.timestamp = -1
            self.unhadled_to_feed_to_detection = 10
            self.insert_bgp_entries = []
            self.update_bgp_entries = []
            self.handled_bgp_entries = []
            self.tmp_hijacks_dict = dict()

            # DB variables
            self.db_conn = None
            self.db_cur = None
            self.create_connect_db()

            # EXCHANGES
            self.config_exchange = Exchange('config', type='direct', durable=False, delivery_mode=1)
            self.update_exchange = Exchange('bgp_update', type='direct', durable=False, delivery_mode=1)
            self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
            self.handled_exchange = Exchange('handled_update', type='direct', durable=False, delivery_mode=1)
            self.db_clock_exchange = Exchange('db_clock', type='direct', durable=False, delivery_mode=1)

            #self.hijack_resolve = Exchange('hijack_resolve', type='direct', durable=False, delivery_mode=1)
            #self.hijack_mit_started = Exchange('hijack_mit_started', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.update_queue = Queue(uuid(), exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                    consumer_arguments={'x-priority': 1})
            self.hijack_queue = Queue(uuid(), exchange=self.hijack_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                    consumer_arguments={'x-priority': 1})
            self.handled_queue = Queue(uuid(), exchange=self.handled_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                    consumer_arguments={'x-priority': 1})
            self.config_queue = Queue(uuid(), exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.db_clock_queue = Queue(uuid(), exchange=self.db_clock_exchange, routing_key='db_clock', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 3})

            self.config_request_rpc()
            self.flag = True
            log.info('SQLite Started..')


        def get_consumers(self, Consumer, channel):
            return [
                    Consumer(
                        queues=[self.config_queue],
                        on_message=self.handle_config_notify,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    Consumer(
                        queues=[self.update_queue],
                        on_message=self.handle_bgp_update,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    Consumer(
                        queues=[self.hijack_queue],
                        on_message=self.handle_hijack,
                        prefetch_count=1,
                        no_ack=True,
                        accept=['pickle']
                        ),
                    Consumer(
                        queues=[self.db_clock_queue],
                        on_message=self._scheduler_instruction,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    Consumer(
                        queues=[self.handled_queue],
                        on_message=self.handle_handled_bgp_update,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    ]

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
                        queues=[callback_queue],
                        no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()

        def handle_bgp_update(self, message):
            msg_ = message.payload
            # prefix, key, origin_as, peer_as, as_path, service, type, communities, timestamp, hijack_id, handled, matched_prefix
            extract_msg = (msg_['prefix'], msg_['key'], str(msg_['path'][-1]), str(msg_['peer_asn']), msg_['path'], msg_['service'], \
                msg_['type'], json.dumps([(k['asn'],k['value']) for k in msg_['communities']]), float(msg_['timestamp']), 0, False, self.find_best_prefix_match(msg_['prefix']) )
            self.insert_bgp_entries.append(extract_msg)

        def handle_hijack(self, message):
            msg_ = message.payload
            key = msg_['key']
            if key not in self.tmp_hijacks_dict:
                self.tmp_hijacks_dict[key] = {}
                self.tmp_hijacks_dict[key]['prefix'] = msg_['prefix']
                self.tmp_hijacks_dict[key]['hijacker'] = str(msg_['hijacker'])
                self.tmp_hijacks_dict[key]['hij_type'] = str(msg_['hij_type'])
                self.tmp_hijacks_dict[key]['time_started'] = msg_['time_started']
                self.tmp_hijacks_dict[key]['time_last'] = msg_['time_last']
                self.tmp_hijacks_dict[key]['peers_seen'] = msg_['peers_seen']
                self.tmp_hijacks_dict[key]['inf_asns'] = msg_['inf_asns']
                self.tmp_hijacks_dict[key]['monitor_keys'] = msg_['monitor_keys']
            else:
                self.tmp_hijacks_dict[key]['time_started'] = min(self.tmp_hijacks_dict[key]['time_started'], msg_['time_started'])
                self.tmp_hijacks_dict[key]['time_last'] = max(self.tmp_hijacks_dict[key]['time_last'], msg_['time_last'])
                self.tmp_hijacks_dict[key]['peers_seen'].update(msg_['peers_seen'])
                self.tmp_hijacks_dict[key]['inf_asns'].update(msg_['inf_asns'])
                self.tmp_hijacks_dict[key]['monitor_keys'].update(msg_['monitor_keys'])

        def handle_handled_bgp_update(self, message):
            msg_ = message.payload
            # prefix, origin_as, peer_as, as_path, service, type, communities, timestamp, hijack_id, handled, matched_prefix, key
            extract_msg = (msg_['prefix'], str(msg_['path'][-1]), str(msg_['peer_asn']), msg_['path'], msg_['service'], \
                msg_['type'], json.dumps([(k['asn'],k['value']) for k in msg_['communities']]), float(msg_['timestamp']), 0, True, self.find_best_prefix_match(msg_['prefix']),  msg_['key'])
            self.handled_bgp_entries.append(extract_msg)


        def build_radix_tree(self):
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                for prefix in rule['prefixes']:
                    node = self.prefix_tree.search_exact(prefix)
                    if node is None:
                        node = self.prefix_tree.add(prefix)
                        node.data['confs'] = []

                    conf_obj = {'origin_asns': rule['origin_asns'], 'neighbors': rule['neighbors']}
                    node.data['confs'].append(conf_obj)

        def find_best_prefix_match(self, prefix):
            prefix_node = self.prefix_tree.search_best(prefix)
            if prefix_node is not None:
                return prefix_node.prefix
            else:
                return ""

        def handle_config_notify(self, message):
            log.info(' [x] PostgreSQL_db - Config Notify')
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.build_radix_tree()

        def handle_config_request_reply(self, message):
            log.info(' [x] PostgreSQL_db - Received Configuration')
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                if raw['timestamp'] > self.timestamp:
                    self.timestamp = raw['timestamp']
                    self.rules = raw.get('rules', [])
                    self.build_radix_tree()

        def create_tables(self):
            bgp_updates_table = "CREATE TABLE IF NOT EXISTS bgp_updates ( " + \
                "id INTEGER GENERATED ALWAYS AS IDENTITY, " + \
                "key VARCHAR ( 32 ) NOT NULL PRIMARY KEY, " + \
                "prefix inet, " + \
                "origin_as VARCHAR ( 6 ), " + \
                "peer_asn   VARCHAR ( 6 ), " + \
                "as_path   text[], " + \
                "service   VARCHAR ( 50 ), " + \
                "type  VARCHAR ( 1 ), " + \
                "communities  json, " + \
                "timestamp REAL, " + \
                "hijack_key VARCHAR ( 32 ), " + \
                "handled   BOOLEAN, " + \
                "matched_prefix inet )"

            bgp_hijacks_table = "CREATE TABLE IF NOT EXISTS hijacks ( " + \
                "id   INTEGER GENERATED ALWAYS AS IDENTITY, " + \
                "key VARCHAR ( 32 ) NOT NULL PRIMARY KEY, " + \
                "type  VARCHAR ( 1 ), " + \
                "prefix    inet, " + \
                "hijack_as VARCHAR ( 6 ), " + \
                "num_peers_seen   INTEGER, " + \
                "num_asns_inf INTEGER, " + \
                "time_started REAL, " + \
                "time_last REAL, " + \
                "time_ended   REAL, " + \
                "mitigation_started   REAL, " + \
                "to_mitigate  BOOLEAN)"

            self.db_cur.execute(bgp_updates_table)
            self.db_cur.execute(bgp_hijacks_table)
            self.db_conn.commit()

        def create_connect_db(self):
            try:
                connect_str = "dbname='artemis_db' user='artemis_user' host='postgres' " + \
                    "password='Art3m1s'"
                self.db_conn = psycopg2.connect(connect_str)
                self.db_cur = self.db_conn.cursor()
                self.create_tables()
            except Exception as e:
                log.info('Error on Postgresql_db creation/connection: ' + str(e))
            finally:
                log.info('PostgreSQL DB created/connected..')


        def _insert_bgp_updates(self):
            try:
                self.db_cur.executemany("INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, " + \
                    "timestamp, hijack_key, handled, matched_prefix) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;", self.insert_bgp_entries)
                self.db_conn.commit()
            except Exception as e:
                log.info("error on _insert_bgp_updates " + str(e))
                self.db_conn.rollback()
                return -1
            finally:
                num_of_entries = len(self.insert_bgp_entries)
                self.insert_bgp_entries.clear()
                return num_of_entries

        def _update_bgp_updates(self):
            num_of_updates = 0
            # Update the BGP entries using the hijack messages
            for hijack_key in self.tmp_hijacks_dict:
                for bgp_entry_to_update in self.tmp_hijacks_dict[hijack_key]['monitor_keys']:
                    num_of_updates += 1
                    self.update_bgp_entries.append((True, str(hijack_key), bgp_entry_to_update))

            if len(self.update_bgp_entries) > 0:
                try:
                    self.db_cur.executemany("UPDATE bgp_updates SET handled=%s, hijack_key=%s WHERE key=%s ", self.update_bgp_entries)
                    self.db_conn.commit()
                except Exception as e:
                    log.info("error on 1_update_bgp_updates " + str(e))
                    self.db_conn.rollback()
                    return -1

            # Update the BGP entries using the handled messages
            if len(self.handled_bgp_entries) > 0:
                try:
                    self.db_cur.executemany("UPDATE bgp_updates SET prefix=%s, origin_as=%s, peer_asn=%s, as_path=%s, service=%s, type=%s, communities=%s, timestamp=%s, hijack_key=%s, handled=%s, matched_prefix=%s " \
                        + " WHERE key=%s", self.handled_bgp_entries)
                    self.db_conn.commit()
                except Exception as e:
                    log.info("error on 2_update_bgp_updates " + str(e))
                    self.db_conn.rollback()
                    return -1

            num_of_updates += len(self.handled_bgp_entries)
            self.handled_bgp_entries.clear()
            return num_of_updates


        def _insert_update_hijacks(self):
            for key in self.tmp_hijacks_dict:
                try:
                    cmd_ = "INSERT INTO hijacks (key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, "
                    cmd_ += "time_started, time_last, time_ended, mitigation_started, to_mitigate) VALUES ("
                    cmd_ += "'" + str(key) + "','" + self.tmp_hijacks_dict[key]['hij_type'] + "','" + self.tmp_hijacks_dict[key]['prefix'] + "','" + self.tmp_hijacks_dict[key]['hijacker'] + "'," 
                    cmd_ += str(len(self.tmp_hijacks_dict[key]['peers_seen'])) + "," + str(len(self.tmp_hijacks_dict[key]['inf_asns'])) + "," + str(self.tmp_hijacks_dict[key]['time_started']) + "," 
                    cmd_ += str(self.tmp_hijacks_dict[key]['time_last']) + ",0,0,false) "
                    cmd_ += "ON CONFLICT(key) DO UPDATE SET num_peers_seen=" + str(len(self.tmp_hijacks_dict[key]['peers_seen'])) + ", num_asns_inf=" + str(len(self.tmp_hijacks_dict[key]['inf_asns']))
                    cmd_ += ", time_started=" + str(self.tmp_hijacks_dict[key]['time_started']) + ", time_last=" + str(self.tmp_hijacks_dict[key]['time_last'])

                    self.db_cur.execute(cmd_)
                    self.db_conn.commit()
                except Exception as e:
                    log.info("error on _insert_update_hijacks " + str(e))
                    self.db_conn.rollback()
                    return -1

            num_of_entries = len(self.tmp_hijacks_dict)
            self.tmp_hijacks_dict.clear()
            return num_of_entries

        def _retrieve_unhandled(self):
            results = []
            self.db_cur.execute("SELECT * FROM bgp_updates WHERE handled = false ORDER BY id ASC LIMIT(" + str(self.unhadled_to_feed_to_detection) + ");")
            entries = self.db_cur.fetchall()
            for entry in entries:
                results.append({ 'key' : entry[1], 'prefix' : entry[2], 'origin_as' : entry[3], 'peer_asn' : entry[4], 'as_path': entry[5], \
                  'service' : entry[6], 'type' : entry[7], 'communities' : entry[8], 'timestamp' : entry[9]})

            self.producer.publish(
                results,
                exchange = self.update_exchange,
                routing_key = 'unhandled',
                retry = False,
                priority = 2
            )


        def _update_bulk(self):
            details = "\n - \tBGP Entries: Inserted %d | Updated %d" % (self._insert_bgp_updates(), self._update_bgp_updates())
            details += "\n - \tHijacks Entries: Inserted/Updated %d" % (self._insert_update_hijacks())
            log.info("[.] SQLite bulk-query execution:" + details)

        def _scheduler_instruction(self, message):
            msg_ = message.payload
            if (msg_ == 'bulk_operation'):
                self._update_bulk()
                return
            elif(msg_ == 'send_unhandled'):
                self._retrieve_unhandled()
                return
            else:
                log.info("Received uknown instruction from scheduler.")
                log.info(msg_)



















