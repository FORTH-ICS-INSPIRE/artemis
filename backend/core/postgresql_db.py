import psycopg2
import radix
from utils import RABBITMQ_HOST
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import time
import pickle
import json
import logging
import hashlib
import os
import datetime

log = logging.getLogger('artemis_logger')


class Postgresql_db(Service):

    def create_connect_db(self):
        _db_conn = None
        time_sleep_connection_retry = 5
        while(_db_conn is None):
            time.sleep(time_sleep_connection_retry)
            try:
                _db_name = os.getenv('DATABASE_NAME', 'artemis_db')
                _user = os.getenv('DATABASE_USER', 'artemis_user')
                _host = os.getenv('DATABASE_HOST', 'postgres')
                _password = os.getenv('DATABASE_PASSWORD', 'Art3m1s')

                _db_conn = psycopg2.connect(
                    dbname=_db_name,
                    user=_user,
                    host=_host,
                    password=_password
                )

            except Exception:
                log.exception('exception')
            finally:
                log.debug('PostgreSQL DB created/connected..')

        return _db_conn

    def run_worker(self):
        db_conn = self.create_connect_db()
        db_cursor = db_conn.cursor()
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection, db_conn, db_cursor)
                self.worker.run()
        except Exception:
            log.exception('exception')
        finally:
            log.info('stopped')
            db_cursor.close()
            db_conn.close()

    class Worker(ConsumerProducerMixin):

        def __init__(self, connection, db_conn, db_cursor):
            self.connection = connection
            self.prefix_tree = None
            self.rules = None
            self.timestamp = -1
            self.num_of_unhadled_to_feed_to_detection = 50
            self.insert_bgp_entries = []
            self.update_bgp_entries = []
            self.handled_bgp_entries = []
            self.tmp_hijacks_dict = dict()

            # DB variables
            self.db_conn = db_conn
            self.db_cur = db_cursor
            self.create_tables()

            # EXCHANGES
            self.config_exchange = Exchange(
                'config',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.update_exchange = Exchange(
                'bgp-update',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.update_exchange.declare()

            self.hijack_exchange = Exchange(
                'hijack-update',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.hijack_exchange.declare()
            self.handled_exchange = Exchange(
                'handled-update', type='direct', durable=False, delivery_mode=1)
            self.db_clock_exchange = Exchange(
                'db-clock', type='direct', durable=False, delivery_mode=1)
            self.mitigation_exchange = Exchange(
                'mitigation', type='direct', durable=False, delivery_mode=1)

            # QUEUES
            self.update_queue = Queue('db-bgp-update', exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                      consumer_arguments={'x-priority': 1})
            self.hijack_queue = Queue('db-hijack-update', exchange=self.hijack_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                      consumer_arguments={'x-priority': 1})
            self.hijack_update_retrieve = Queue('db-hijack-fetch', exchange=self.hijack_exchange, routing_key='fetch-hijacks', durable=False, exclusive=True, max_priority=1,
                                                consumer_arguments={'x-priority': 2})
            self.hijack_resolved_queue = Queue('db-hijack-resolve', exchange=self.hijack_exchange, routing_key='resolved', durable=False, exclusive=True, max_priority=2,
                                               consumer_arguments={'x-priority': 2})
            self.hijack_ignored_queue = Queue('db-hijack-ignored', exchange=self.hijack_exchange, routing_key='ignored', durable=False, exclusive=True, max_priority=2,
                                              consumer_arguments={'x-priority': 2})
            self.handled_queue = Queue('db-handled-update', exchange=self.handled_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                       consumer_arguments={'x-priority': 1})
            self.config_queue = Queue('db-config-notify', exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=2,
                                      consumer_arguments={'x-priority': 2})
            self.db_clock_queue = Queue('db-db-clock', exchange=self.db_clock_exchange, routing_key='db-clock-message', durable=False, exclusive=True, max_priority=2,
                                        consumer_arguments={'x-priority': 3})
            self.mitigate_queue = Queue('db-mitigation-start', exchange=self.mitigation_exchange, routing_key='mit-start', durable=False, exclusive=True, max_priority=2,
                                        consumer_arguments={'x-priority': 2})
            self.hijack_comment_queue = Queue('db-hijack-comment', durable=False, max_priority=4,
                                              consumer_arguments={'x-priority': 4})

            self.config_request_rpc()
            log.info('started')

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
                    on_message=self.handle_hijack_update,
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
                Consumer(
                    queues=[self.hijack_update_retrieve],
                    on_message=self.handle_hijack_retrieve,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_resolved_queue],
                    on_message=self.handle_resolved_hijack,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.mitigate_queue],
                    on_message=self.handle_mitigation_request,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_ignored_queue],
                    on_message=self.handle_hijack_ignore_request,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_comment_queue],
                    on_message=self.handle_hijack_comment,
                    prefetch_count=1,
                    no_ack=True
                )
            ]

        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(),
                                   durable=False,
                                   auto_delete=True,
                                   max_priority=4,
                                   consumer_arguments={
                'x-priority': 4})

            self.producer.publish(
                '',
                exchange='',
                routing_key='config-request-queue',
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        'config-request-queue',
                        durable=False,
                        max_priority=4,
                        consumer_arguments={
                            'x-priority': 4}),
                    callback_queue
                ],
                priority=4
            )
            with Consumer(self.connection,
                          on_message=self.handle_config_request_reply,
                          queues=[callback_queue],
                          no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()

        def handle_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            msg_ = message.payload
            # prefix, key, origin_as, peer_asn, as_path, service, type, communities,
            # timestamp, hijack_key, handled, matched_prefix, orig_path
            origin_as = -1
            if len(msg_['path']) >= 1:
                origin_as = msg_['path'][-1]

            try:
                extract_msg = (
                    msg_['prefix'],  # prefix
                    msg_['key'],  # key
                    int(origin_as),  # origin_as
                    int(msg_['peer_asn']),  # peer_asn
                    msg_['path'],  # as_path
                    msg_['service'],  # service
                    msg_['type'],   # type
                    json.dumps([(k['asn'], k['value'])
                                for k in msg_['communities']]),  # communities
                    datetime.datetime.fromtimestamp(
                        (int(msg_['timestamp']))),  # timestamp
                    None,  # hijack_key
                    False,  # handled
                    self.find_best_prefix_match(
                        msg_['prefix']),  # matched_prefix
                    json.dumps(msg_['orig_path'])  # orig_path
                )
                self.insert_bgp_entries.append(extract_msg)
            except Exception:
                log.debug("exception: {}".format(msg_))

        def handle_hijack_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            msg_ = message.payload
            try:
                key = msg_['key']
                if key not in self.tmp_hijacks_dict:
                    self.tmp_hijacks_dict[key] = {}
                    self.tmp_hijacks_dict[key]['prefix'] = msg_['prefix']
                    self.tmp_hijacks_dict[key]['hijack_as'] = int(
                        msg_['hijack_as'])
                    self.tmp_hijacks_dict[key]['type'] = str(
                        msg_['type'])
                    self.tmp_hijacks_dict[key]['time_started'] = int(
                        msg_['time_started'])
                    self.tmp_hijacks_dict[key]['time_last'] = int(
                        msg_['time_last'])
                    self.tmp_hijacks_dict[key]['peers_seen'] = json.dumps(list(msg_[
                        'peers_seen']))
                    self.tmp_hijacks_dict[key]['asns_inf'] = json.dumps(list(msg_[
                        'asns_inf']))
                    self.tmp_hijacks_dict[key]['num_peers_seen'] = len(msg_[
                        'peers_seen'])
                    self.tmp_hijacks_dict[key]['num_asns_inf'] = len(msg_[
                        'asns_inf'])
                    self.tmp_hijacks_dict[key]['monitor_keys'] = msg_[
                        'monitor_keys']
                    self.tmp_hijacks_dict[key]['time_detected'] = int(
                        msg_['time_detected'])
                    self.tmp_hijacks_dict[key]['configured_prefix'] = msg_[
                        'configured_prefix']
                    self.tmp_hijacks_dict[key]['timestamp_of_config'] = int(
                        msg_['timestamp_of_config'])
                else:
                    self.tmp_hijacks_dict[key]['time_started'] = int(
                        min(self.tmp_hijacks_dict[key]['time_started'], msg_['time_started']))
                    self.tmp_hijacks_dict[key]['time_last'] = int(
                        max(self.tmp_hijacks_dict[key]['time_last'], msg_['time_last']))
                    self.tmp_hijacks_dict[key]['peers_seen'] = json.dumps(list(msg_[
                        'peers_seen']))
                    self.tmp_hijacks_dict[key]['asns_inf'] = json.dumps(list(msg_[
                        'asns_inf']))
                    self.tmp_hijacks_dict[key]['num_peers_seen'] = len(msg_[
                        'peers_seen'])
                    self.tmp_hijacks_dict[key]['num_asns_inf'] = len(msg_[
                        'asns_inf'])
                    self.tmp_hijacks_dict[key]['monitor_keys'].update(
                        msg_['monitor_keys'])
            except Exception:
                log.debug("exception: {}".format(msg_))

        def handle_handled_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            try:
                key_ = (message.payload,)
                self.handled_bgp_entries.append(key_)
            except Exception:
                log.debug("exception: {}".format(message))

        def build_radix_tree(self):
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                for prefix in rule['prefixes']:
                    node = self.prefix_tree.search_exact(prefix)
                    if node is None:
                        node = self.prefix_tree.add(prefix)
                        node.data['confs'] = []

                    conf_obj = {
                        'origin_asns': rule['origin_asns'],
                        'neighbors': rule['neighbors']}
                    node.data['confs'].append(conf_obj)

        def find_best_prefix_match(self, prefix):
            prefix_node = self.prefix_tree.search_best(prefix)
            if prefix_node is not None:
                return prefix_node.prefix
            else:
                return None

        def handle_config_notify(self, message):
            log.debug(
                'Message: {}\npayload: {}'.format(
                    message, message.payload))
            config = message.payload
            try:
                if config['timestamp'] > self.timestamp:
                    self.timestamp = config['timestamp']
                    self.rules = config.get('rules', [])
                    self.build_radix_tree()
                    if 'timestamp' in config:
                        del config['timestamp']
                    raw_config = ""
                    if 'raw_config' in config:
                        raw_config = config['raw_config']
                        del config['raw_config']
                    config_hash = hashlib.md5(pickle.dumps(config)).hexdigest()
                    self._save_config(config_hash, config, raw_config)
            except Exception:
                log.debug("exception: {}".format(config))

        def handle_config_request_reply(self, message):
            log.debug(
                'Message: {}\npayload: {}'.format(
                    message, message.payload))
            config = message.payload
            try:
                if self.correlation_id == message.properties['correlation_id']:
                    if config['timestamp'] > self.timestamp:
                        self.timestamp = config['timestamp']
                        self.rules = config.get('rules', [])
                        self.build_radix_tree()
                        if 'timestamp' in config:
                            del config['timestamp']
                        raw_config = ""
                        if 'raw_config' in config:
                            raw_config = config['raw_config']
                            del config['raw_config']
                        config_hash = hashlib.md5(
                            pickle.dumps(config)).hexdigest()
                        latest_config_in_db_hash = self._retrieve_most_recent_config_hash()
                        if config_hash != latest_config_in_db_hash:
                            self._save_config(config_hash, config, raw_config)
                        else:
                            log.debug("database config is up-to-date")
            except Exception:
                log.debug("exception: {}".format(config))

        def handle_hijack_retrieve(self, message):
            """
            handle_hijack_retrieve:
            Return all active hijacks
            Used in detection memcache
            """
            time.sleep(5)
            log.debug("received hijack_retrieve")
            try:
                results = {}
                cmd_ = "SELECT time_started, time_last, peers_seen, "
                cmd_ += "asns_inf, key, prefix, hijack_as, type, time_detected, "
                cmd_ += "configured_prefix, timestamp_of_config "
                cmd_ += "FROM hijacks WHERE active = true;"
                self.db_cur.execute(cmd_)
                entries = self.db_cur.fetchall()
                for entry in entries:
                    results[entry[4]] = {
                        'time_started': int(entry[0].timestamp()),
                        'time_last': int(entry[1].timestamp()),
                        'peers_seen': set(entry[2]),
                        'asns_inf': set(entry[3]),
                        'key': entry[4],
                        'prefix': str(entry[5]),
                        'hijack_as': int(entry[6]),
                        'type': entry[7],
                        'time_detected': int(entry[8].timestamp()),
                        'configured_prefix': str(entry[9]),
                        'timestamp_of_config': int(entry[10].timestamp())
                    }

                self.producer.publish(
                    results,
                    exchange=self.hijack_exchange,
                    routing_key='fetch',
                    serializer='pickle',
                    retry=False,
                    priority=2
                )
            except Exception:
                log.exception("exception")

        def handle_resolved_hijack(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.db_cur.execute(
                    "UPDATE hijacks SET active=false, under_mitigation=false, resolved=true, time_ended=%s WHERE key=%s;",
                    (datetime.datetime.now(), raw['key'],))
                self.db_conn.commit()
            except Exception:
                log.exception('exception: {}'.format(raw))

        def handle_mitigation_request(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.db_cur.execute(
                    "UPDATE hijacks SET mitigation_started=%s, under_mitigation=true WHERE key=%s;",
                    (datetime.datetime.fromtimestamp(
                        int(raw['time'])),
                        raw['key']))
                self.db_conn.commit()
            except Exception:
                log.exception('exception: {}'.format(raw))

        def handle_hijack_ignore_request(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.db_cur.execute(
                    "UPDATE hijacks SET active=false, under_mitigation=false, ignored=true WHERE key=%s;",
                    (raw['key'],
                     ))
                self.db_conn.commit()
            except Exception:
                log.exception('exception: {}'.format(raw))

        def handle_hijack_comment(self, message):
            raw = message.payload
            log.debug("payload: {}".format(raw))
            try:
                self.db_cur.execute(
                    "UPDATE hijacks SET comment=%s WHERE key=%s;", (raw['comment'], raw['key']))
                self.db_conn.commit()
                self.producer.publish(
                    {
                        'status': 'accepted'
                    },
                    exchange='',
                    routing_key=message.properties['reply_to'],
                    correlation_id=message.properties['correlation_id'],
                    serializer='json',
                    retry=True,
                    priority=4
                )
            except Exception:
                self.producer.publish(
                    {
                        'status': 'fail'
                    },
                    exchange='',
                    routing_key=message.properties['reply_to'],
                    correlation_id=message.properties['correlation_id'],
                    serializer='json',
                    retry=True,
                    priority=4
                )
                log.exception('exception: {}'.format(raw))

        def create_tables(self):
            timescale_extension = "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

            bgp_updates_table = "CREATE TABLE IF NOT EXISTS bgp_updates ( " + \
                "key VARCHAR ( 32 ) NOT NULL, " + \
                "prefix inet, " + \
                "origin_as INTEGER, " + \
                "peer_asn   INTEGER, " + \
                "as_path   text[], " + \
                "service   VARCHAR ( 50 ), " + \
                "type  VARCHAR ( 1 ), " + \
                "communities  json, " + \
                "timestamp TIMESTAMP  NOT NULL, " + \
                "hijack_key VARCHAR ( 32 ), " + \
                "handled   BOOLEAN, " + \
                "matched_prefix inet, " + \
                "orig_path json, " + \
                "PRIMARY KEY(timestamp, key), " + \
                "UNIQUE(timestamp, key));"

            timescale_bgp_updates = "SELECT create_hypertable('bgp_updates', 'timestamp', if_not_exists => TRUE);"

            bgp_hijacks_table = "CREATE TABLE IF NOT EXISTS hijacks ( " + \
                "key VARCHAR ( 32 ) NOT NULL, " + \
                "type  VARCHAR ( 1 ), " + \
                "prefix    inet, " + \
                "hijack_as INTEGER, " + \
                "peers_seen   json, " + \
                "num_peers_seen INTEGER, " + \
                "asns_inf json, " + \
                "num_asns_inf INTEGER, " + \
                "time_started TIMESTAMP, " + \
                "time_last TIMESTAMP, " + \
                "time_ended   TIMESTAMP, " + \
                "mitigation_started   TIMESTAMP, " + \
                "time_detected TIMESTAMP  NOT NULL," + \
                "under_mitigation BOOLEAN, " + \
                "resolved  BOOLEAN, " + \
                "active  BOOLEAN, " + \
                "ignored BOOLEAN,  " + \
                "configured_prefix  inet, " + \
                "timestamp_of_config TIMESTAMP, " + \
                "comment text, " + \
                "PRIMARY KEY(time_detected, key), " + \
                "UNIQUE(time_detected, key), " + \
                "CONSTRAINT possible_states CHECK ( (active=true and under_mitigation=false and resolved=false and ignored=false) or " + \
                "(active=true and under_mitigation=true and resolved=false and ignored=false) or " + \
                "(active=false and under_mitigation=false and resolved=true and ignored=false) or " + \
                "(active=false and under_mitigation=false and resolved=false and ignored=true)))"

            timescale_hijacks = "SELECT create_hypertable('hijacks', 'time_detected', if_not_exists => TRUE);"

            configs_table = "CREATE TABLE IF NOT EXISTS configs ( " + \
                "key VARCHAR ( 32 ) NOT NULL, " + \
                "config_data  json, " + \
                "raw_config  text, " + \
                "comment text, " + \
                "time_modified TIMESTAMP NOT NULL) "

            config_view = "CREATE OR REPLACE VIEW view_configs AS SELECT time_modified "
            config_view += "FROM configs;"

            hijacks_view = "CREATE OR REPLACE VIEW view_hijacks AS SELECT key,"
            hijacks_view += "type, prefix, hijack_as, num_peers_seen, num_asns_inf, "
            hijacks_view += "time_started, time_ended, time_last, mitigation_started, "
            hijacks_view += "time_detected, timestamp_of_config, under_mitigation, resolved, active, "
            hijacks_view += "ignored, configured_prefix, comment FROM hijacks;"

            bgp_updates_view = "CREATE OR REPLACE VIEW view_bgpupdates AS SELECT prefix, origin_as, peer_asn, "
            bgp_updates_view += "as_path, service, type, communities, timestamp, "
            bgp_updates_view += "hijack_key, handled, matched_prefix, orig_path FROM bgp_updates;"

            self.db_cur.execute(timescale_extension)

            self.db_cur.execute(bgp_updates_table)
            self.db_cur.execute(timescale_bgp_updates)

            self.db_cur.execute(bgp_hijacks_table)
            self.db_cur.execute(timescale_hijacks)

            self.db_cur.execute(configs_table)
            self.db_cur.execute(config_view)
            self.db_cur.execute(bgp_updates_view)
            self.db_cur.execute(hijacks_view)

            self.db_conn.commit()

        def _insert_bgp_updates(self):
            try:
                cmd_ = "INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, "
                cmd_ += "timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES "
                cmd_ += "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT(key, timestamp) DO NOTHING;"
                self.db_cur.executemany(cmd_, self.insert_bgp_entries)
                self.db_conn.commit()
            except Exception:
                log.exception('exception')
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
                    self.update_bgp_entries.append(
                        (str(hijack_key), bgp_entry_to_update))

            if len(self.update_bgp_entries) > 0:
                try:
                    self.db_cur.executemany(
                        "UPDATE bgp_updates SET handled=true, hijack_key=%s WHERE key=%s ",
                        self.update_bgp_entries)
                    self.db_conn.commit()
                except Exception:
                    log.exception('exception')
                    self.db_conn.rollback()
                    return -1

            # Update the BGP entries using the handled messages
            if len(self.handled_bgp_entries) > 0:
                try:
                    self.db_cur.executemany(
                        "UPDATE bgp_updates SET handled=true WHERE key=%s",
                        self.handled_bgp_entries)
                    self.db_conn.commit()
                except Exception:
                    log.exception(
                        'handled bgp entries {}'.format(
                            self.handled_bgp_entries))
                    self.db_conn.rollback()
                    return -1

            num_of_updates += len(self.handled_bgp_entries)
            self.handled_bgp_entries.clear()
            return num_of_updates

        def _insert_update_hijacks(self):
            for key in self.tmp_hijacks_dict:
                try:
                    cmd_ = "INSERT INTO hijacks (key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, "
                    cmd_ += "time_started, time_last, time_ended, mitigation_started, time_detected, under_mitigation, "
                    cmd_ += "active, resolved, ignored, configured_prefix, timestamp_of_config, comment, peers_seen, asns_inf) "
                    cmd_ += "VALUES (%s, %s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    cmd_ += "ON CONFLICT(key, time_detected) DO UPDATE SET num_peers_seen=%s, num_asns_inf=%s, time_started=%s, "
                    cmd_ += "time_last=%s, peers_seen=%s, asns_inf=%s;"

                    values_ = (
                        key,  # key
                        self.tmp_hijacks_dict[key]['type'],  # type
                        self.tmp_hijacks_dict[key]['prefix'],  # prefix
                        self.tmp_hijacks_dict[key]['hijack_as'],  # hijack_as
                        # num_peers_seen
                        self.tmp_hijacks_dict[key]['num_peers_seen'],
                        # num_asns_inf
                        self.tmp_hijacks_dict[key]['num_asns_inf'],
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['time_started'])),  # time_started
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['time_last'])),  # time_last
                        None,  # time_ended
                        None,  # mitigation_started
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['time_detected'])),  # time_detected
                        False,  # under_mitigation
                        True,  # active
                        False,  # resolved
                        False,  # ignored
                        # configured_prefix
                        self.tmp_hijacks_dict[key]['configured_prefix'],
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['timestamp_of_config'])),  # timestamp_of_config
                        '',  # comment
                        self.tmp_hijacks_dict[key]['peers_seen'],  # peers_seen
                        self.tmp_hijacks_dict[key]['asns_inf'],  # asns_inf
                        # num_peers_seen
                        self.tmp_hijacks_dict[key]['num_peers_seen'],
                        # num_asns_inf
                        self.tmp_hijacks_dict[key]['num_asns_inf'],
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['time_started'])),  # time_started
                        datetime.datetime.fromtimestamp(
                            int(self.tmp_hijacks_dict[key]['time_last'])),  # time_last
                        self.tmp_hijacks_dict[key]['peers_seen'],  # peers_seen
                        self.tmp_hijacks_dict[key]['asns_inf']  # asns_inf
                    )

                    self.db_cur.execute(cmd_, values_)
                    self.db_conn.commit()
                except Exception:
                    log.exception('exception')
                    self.db_conn.rollback()
                    return -1

            num_of_entries = len(self.tmp_hijacks_dict)
            self.tmp_hijacks_dict.clear()
            return num_of_entries

        def _retrieve_unhandled(self):
            results = []
            cmd_ = "SELECT key, prefix, origin_as, peer_asn, as_path, service, "
            cmd_ += "type, communities, timestamp FROM bgp_updates WHERE "
            cmd_ += "handled = false ORDER BY timestamp DESC LIMIT(%s);"
            self.db_cur.execute(
                cmd_, (self.num_of_unhadled_to_feed_to_detection,))
            entries = self.db_cur.fetchall()
            for entry in entries:
                results.append({
                    'key': entry[0],  # key
                    'prefix': entry[1],  # prefix
                    'origin_as': entry[2],  # origin_as
                    'peer_asn': entry[3],  # peer_asn
                    'path': entry[4],  # as_path
                    'service': entry[5],  # service
                    'type': entry[6],  # type
                    'communities': entry[7],  # communities
                    'timestamp': int(entry[8].timestamp())
                })
            if len(results):
                self.producer.publish(
                    results,
                    exchange=self.update_exchange,
                    routing_key='unhandled',
                    retry=False,
                    priority=2
                )

        def _update_bulk(self):
            inserts, updates, hijacks = self._insert_bgp_updates(
            ), self._update_bgp_updates(), self._insert_update_hijacks()
            str_ = ""
            if inserts > 0:
                str_ += "BGP Updates Inserted: {}\n".format(inserts)
            if updates > 0:
                str_ += "BGP Updates Updated: {}\n".format(updates)
            if hijacks > 0:
                str_ += "Hijacks Inserted: {}".format(hijacks)
            if str_ != "":
                log.debug('{}'.format(str_))

        def _scheduler_instruction(self, message):
            msg_ = message.payload
            if (msg_ == 'bulk_operation'):
                self._update_bulk()
                return
            elif(msg_ == 'send_unhandled'):
                self._retrieve_unhandled()
                return
            else:
                log.warning(
                    'Received uknown instruction from scheduler: {}'.format(msg_))

        def _save_config(self, config_hash, yaml_config, raw_config):
            try:
                log.debug("Config Store..")
                cmd_ = "INSERT INTO configs (key, config_data, raw_config, time_modified)"
                cmd_ += "VALUES (%s, %s, %s, %s);"
                self.db_cur.execute(
                    cmd_,
                    (config_hash,
                     json.dumps(yaml_config),
                        raw_config,
                        datetime.datetime.now()))
                self.db_conn.commit()
            except Exception:
                log.exception("failed to save config in db")

        def _retrieve_most_recent_config_hash(self):
            try:
                self.db_cur.execute(
                    "SELECT key from configs ORDER BY time_modified DESC LIMIT 1")
                hash_ = self.db_cur.fetchone()
                if isinstance(hash_, tuple):
                    return hash_[0]
            except Exception:
                log.exception(
                    "failed to retrieved most recent config hash in db")
            return None
