import psycopg2
import psycopg2.extras
import radix
from utils import RABBITMQ_HOST, get_logger, redis_key
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import time
import pickle
import json
import signal
import hashlib
import os
import datetime
import redis

log = get_logger()
TABLES = ['bgp_updates', 'hijacks', 'configs']
VIEWS = ['view_configs', 'view_bgpupdates', 'view_hijacks']


class Postgresql_db():

    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def create_connect_db(self):
        _db_conn = None
        time_sleep_connection_retry = 5
        while _db_conn is None:
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

    def run(self):
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

    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):

        def __init__(self, connection, db_conn, db_cursor):
            self.connection = connection
            self.prefix_tree = None
            self.rules = None
            self.timestamp = -1
            self.insert_bgp_entries = []
            self.insert_bgp_withdrawals = set()
            self.update_bgp_entries = set()
            self.handled_bgp_entries = set()
            self.tmp_hijacks_dict = {}

            # DB variables
            self.db_conn = db_conn
            self.db_cur = db_cursor

            # redis db
            self.redis = redis.Redis(
                host='localhost',
                    port=6379
            )
            self.redis.flushall()
            self.retrieve_hijacks()

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
            self.update_queue = Queue(
                'db-bgp-update', exchange=self.update_exchange, routing_key='update', durable=False, auto_delete=True, max_priority=1,
                                      consumer_arguments={'x-priority': 1})
            self.hijack_queue = Queue(
                'db-hijack-update', exchange=self.hijack_exchange, routing_key='update', durable=False, auto_delete=True, max_priority=1,
                                      consumer_arguments={'x-priority': 1})
            self.hijack_resolved_queue = Queue(
                'db-hijack-resolve', exchange=self.hijack_exchange, routing_key='resolved', durable=False, auto_delete=True, max_priority=2,
                                               consumer_arguments={'x-priority': 2})
            self.hijack_ignored_queue = Queue(
                'db-hijack-ignored', exchange=self.hijack_exchange, routing_key='ignored', durable=False, auto_delete=True, max_priority=2,
                                              consumer_arguments={'x-priority': 2})
            self.handled_queue = Queue(
                'db-handled-update', exchange=self.handled_exchange, routing_key='update', durable=False, auto_delete=True, max_priority=1,
                                       consumer_arguments={'x-priority': 1})
            self.config_queue = Queue(
                'db-config-notify', exchange=self.config_exchange, routing_key='notify', durable=False, auto_delete=True, max_priority=2,
                                      consumer_arguments={'x-priority': 2})
            self.db_clock_queue = Queue(
                'db-db-clock', exchange=self.db_clock_exchange, routing_key='db-clock-message', durable=False, auto_delete=True, max_priority=2,
                                        consumer_arguments={'x-priority': 3})
            self.mitigate_queue = Queue(
                'db-mitigation-start', exchange=self.mitigation_exchange, routing_key='mit-start', durable=False, auto_delete=True, max_priority=2,
                                        consumer_arguments={'x-priority': 2})
            self.hijack_comment_queue = Queue('db-hijack-comment', durable=False, auto_delete=True, max_priority=4,
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
                    prefetch_count=1000,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_queue],
                    on_message=self.handle_hijack_update,
                    prefetch_count=1000,
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
                    prefetch_count=1000,
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
            try:
                origin_as = -1
                if len(msg_['path']) >= 1:
                    origin_as = msg_['path'][-1]

                extract_msg = (
                    msg_['prefix'],  # prefix
                    msg_['key'],  # key
                    origin_as,  # origin_as
                    msg_['peer_asn'],  # peer_asn
                    msg_['path'],  # as_path
                    msg_['service'],  # service
                    msg_['type'],   # type
                    json.dumps([(k['asn'], k['value'])
                                for k in msg_['communities']]),  # communities
                    datetime.datetime.fromtimestamp(
                        (msg_['timestamp'])),  # timestamp
                    None,  # hijack_key
                    False,  # handled
                    self.find_best_prefix_match(
                        msg_['prefix']),  # matched_prefix
                    json.dumps(msg_['orig_path'])  # orig_path
                )
                # insert all types of BGP updates
                self.insert_bgp_entries.append(extract_msg)

                # update hijacks based on withdrawal messages
                if msg_['type'] is 'W':
                    extract_msg = (
                        msg_['prefix'],  # prefix
                        msg_['peer_asn'],  # peer_asn
                        datetime.datetime.fromtimestamp(
                            (msg_['timestamp'])),  # timestamp
                        msg_['key'] # key
                    )
                    self.insert_bgp_withdrawals.add(extract_msg)
            except Exception:
                log.exception('{}'.format(msg_))

        def handle_hijack_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            msg_ = message.payload
            try:
                key = msg_['key']
                if key not in self.tmp_hijacks_dict:
                    self.tmp_hijacks_dict[key] = {}
                    self.tmp_hijacks_dict[key]['prefix'] = msg_['prefix']
                    self.tmp_hijacks_dict[key]['hijack_as'] = msg_['hijack_as']
                    self.tmp_hijacks_dict[key]['type'] = msg_['type']
                    self.tmp_hijacks_dict[key]['time_started'] = msg_['time_started']
                    self.tmp_hijacks_dict[key]['time_last'] = msg_['time_last']
                    self.tmp_hijacks_dict[key]['peers_seen'] = list(msg_['peers_seen'])
                    self.tmp_hijacks_dict[key]['asns_inf'] = list(msg_['asns_inf'])
                    self.tmp_hijacks_dict[key]['num_peers_seen'] = len(msg_['peers_seen'])
                    self.tmp_hijacks_dict[key]['num_asns_inf'] = len(msg_['asns_inf'])
                    self.tmp_hijacks_dict[key]['monitor_keys'] = msg_['monitor_keys']
                    self.tmp_hijacks_dict[key]['time_detected'] = msg_['time_detected']
                    self.tmp_hijacks_dict[key]['configured_prefix'] = msg_['configured_prefix']
                    self.tmp_hijacks_dict[key]['timestamp_of_config'] = msg_['timestamp_of_config']
                else:
                    self.tmp_hijacks_dict[key]['time_started'] = min(self.tmp_hijacks_dict[key]['time_started'], msg_['time_started'])
                    self.tmp_hijacks_dict[key]['time_last'] = max(self.tmp_hijacks_dict[key]['time_last'], msg_['time_last'])
                    self.tmp_hijacks_dict[key]['peers_seen'] = list(msg_['peers_seen'])
                    self.tmp_hijacks_dict[key]['asns_inf'] = list(msg_['asns_inf'])
                    self.tmp_hijacks_dict[key]['num_peers_seen'] = len(msg_[
                        'peers_seen'])
                    self.tmp_hijacks_dict[key]['num_asns_inf'] = len(msg_[
                        'asns_inf'])
                    self.tmp_hijacks_dict[key]['monitor_keys'].update(
                        msg_['monitor_keys'])
            except Exception:
                log.exception('{}'.format(msg_))

        def handle_handled_bgp_update(self, message):
            # log.debug('message: {}\npayload: {}'.format(message, message.payload))
            try:
                key_ = (message.payload,)
                self.handled_bgp_entries.add(key_)
            except Exception:
                log.exception('{}'.format(message))

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
                    raw_config = ''
                    if 'raw_config' in config:
                        raw_config = config['raw_config']
                        del config['raw_config']
                    config_hash = hashlib.md5(pickle.dumps(config)).hexdigest()
                    self._save_config(config_hash, config, raw_config)
            except Exception:
                log.exception('{}'.format(config))

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
                        raw_config = ''
                        if 'raw_config' in config:
                            raw_config = config['raw_config']
                            del config['raw_config']
                        config_hash = hashlib.md5(
                            pickle.dumps(config)).hexdigest()
                        latest_config_in_db_hash = self._retrieve_most_recent_config_hash()
                        if config_hash != latest_config_in_db_hash:
                            self._save_config(config_hash, config, raw_config)
                        else:
                            log.debug('database config is up-to-date')
            except Exception:
                log.exception('{}'.format(config))

        def retrieve_hijacks(self):
            try:
                cmd_ = 'SELECT time_started, time_last, peers_seen, '
                cmd_ += 'asns_inf, key, prefix, hijack_as, type, time_detected, '
                cmd_ += 'configured_prefix, timestamp_of_config '
                cmd_ += 'FROM hijacks WHERE active = true;'
                self.db_cur.execute(cmd_)
                entries = self.db_cur.fetchall()
                redis_pipeline = self.redis.pipeline()
                for entry in entries:
                    result = {
                        'time_started': entry[0].timestamp(),
                        'time_last': entry[1].timestamp(),
                        'peers_seen': set(entry[2]),
                        'asns_inf': set(entry[3]),
                        'key': entry[4],
                        'prefix': entry[5],
                        'hijack_as': entry[6],
                        'type': entry[7],
                        'time_detected': entry[8].timestamp(),
                        'configured_prefix': entry[9],
                        'timestamp_of_config': entry[10].timestamp()
                    }
                    redis_hijack_key = redis_key(
                        entry[5],
                        entry[6],
                        entry[7])
                    # log.info('Set redis hijack key {}'.format(redis_hijack_key))
                    redis_pipeline.set(redis_hijack_key, pickle.dumps(result))
                redis_pipeline.execute()
            except Exception:
                log.exception('exception')

        def handle_resolved_hijack(self, message):
            raw = message.payload
            log.debug('payload: {}'.format(raw))
            try:
                self.db_cur.execute(
                    'UPDATE hijacks SET active=false, under_mitigation=false, resolved=true, time_ended=%s WHERE key=%s;',
                    (datetime.datetime.now(), raw['key'],))
                self.db_conn.commit()
                redis_hijack_key = redis_key(
                     raw['prefix'],
                     raw['hijack_as'],
                     raw['type'])
                self.redis.delete(redis_hijack_key)
            except Exception:
                log.exception('{}'.format(raw))

        def handle_mitigation_request(self, message):
            raw = message.payload
            log.debug('payload: {}'.format(raw))
            try:
                self.db_cur.execute(
                    'UPDATE hijacks SET mitigation_started=%s, under_mitigation=true WHERE key=%s;',
                    (datetime.datetime.fromtimestamp(
                        raw['time']),
                        raw['key']))
                self.db_conn.commit()
            except Exception:
                log.exception('{}'.format(raw))

        def handle_hijack_ignore_request(self, message):
            raw = message.payload
            log.debug('payload: {}'.format(raw))
            try:
                self.db_cur.execute(
                    'UPDATE hijacks SET active=false, under_mitigation=false, ignored=true WHERE key=%s;',
                    (raw['key'],
                     ))
                self.db_conn.commit()
                redis_hijack_key = redis_key(
                     raw['prefix'],
                     raw['hijack_as'],
                     raw['type'])
                self.redis.delete(redis_hijack_key)
            except Exception:
                log.exception('{}'.format(raw))

        def handle_hijack_comment(self, message):
            raw = message.payload
            log.debug('payload: {}'.format(raw))
            try:
                self.db_cur.execute(
                    'UPDATE hijacks SET comment=%s WHERE key=%s;', (raw['comment'], raw['key']))
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
                log.exception('{}'.format(raw))

        def _insert_bgp_updates(self):
            try:
                cmd_ = 'INSERT INTO bgp_updates (prefix, key, origin_as, peer_asn, as_path, service, type, communities, '
                cmd_ += 'timestamp, hijack_key, handled, matched_prefix, orig_path) VALUES '
                cmd_ += '(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT(key, timestamp) DO NOTHING;'
                psycopg2.extras.execute_batch(
                    self.db_cur, cmd_, self.insert_bgp_entries, page_size=1000)
                self.db_conn.commit()
            except Exception:
                log.exception('exception')
                self.db_conn.rollback()
                return -1
            finally:
                num_of_entries = len(self.insert_bgp_entries)
                self.insert_bgp_entries.clear()
                return num_of_entries

        def _handle_bgp_withdrawals(self):
            cmd_ = "SELECT hijacks.peers_seen, hijacks.peers_withdrawn, hijacks.key, hijacks.hijack_as, hijacks.type "
            cmd_ += "FROM bgp_updates, hijacks "
            cmd_ += "WHERE hijacks.active = true AND bgp_updates.hijack_key = hijacks.key "
            cmd_ += "AND bgp_updates.prefix = %s AND bgp_updates.peer_asn = %s AND bgp_updates.timestamp < %s"
            update_bgp_withdrawals = set()
            for withdrawal in self.insert_bgp_withdrawals:
                # 0: prefix, 1: peer_asn, 2: timestamp, 3: key
                try:
                    self.db_cur.execute(cmd_, (withdrawal[0], withdrawal[1], withdrawal[2]))
                    # 0: peers_seen, 1: peers_withdrawn, 2: hij.key, 3: hij.as, 4: hij.type
                    entry = self.db_cur.fetchone()
                    if entry is None:
                        update_bgp_withdrawals.add((None, withdrawal[3]))
                        continue
                    # matching withdraw with a hijack
                    update_bgp_withdrawals.add((entry[2], withdrawal[3]))
                    if withdrawal[1] not in entry[1] and withdrawal[1] in entry[0]:
                        entry[1].append(withdrawal[1])
                        if len(entry[0]) == len(entry[1]):
                            # set hijack as withdrawn and delete from redis
                            self.db_cur.execute(
                                'UPDATE hijacks SET active=false, under_mitigation=false, resolved=false, withdrawn=true, time_ended=%s, peers_withdrawn=%s WHERE key=%s;',
                                (datetime.datetime.now(), entry[1], entry[2],))
                            self.db_conn.commit()
                            log.debug('withdrawn hijack {}'.format(entry))
                            redis_hijack_key = redis_key(
                                withdrawal[0],
                                entry[3],
                                entry[4])
                            self.redis.delete(redis_hijack_key)
                        else:
                            # add withdrawal to hijack
                            self.db_cur.execute(
                                'UPDATE hijacks SET peers_withdrawn=%s WHERE key=%s;',
                                (entry[1], entry[2],))
                            self.db_conn.commit()
                            log.debug('updating hijack {}'.format(entry))
                except Exception:
                    log.exception('exception')

            try:
                psycopg2.extras.execute_batch(
                    self.db_cur,
                    'UPDATE bgp_updates SET handled=true, hijack_key=%s WHERE key=%s ',
                    list(update_bgp_withdrawals),
                    page_size=1000
                )
                self.db_conn.commit()
            except Exception:
                log.exception('exception')
                self.db_conn.rollback()

            num_of_entries = len(self.insert_bgp_withdrawals)
            self.insert_bgp_withdrawals.clear()
            return num_of_entries

        def _update_bgp_updates(self):
            num_of_updates = 0
            # Update the BGP entries using the hijack messages
            for hijack_key in self.tmp_hijacks_dict:
                for bgp_entry_to_update in self.tmp_hijacks_dict[hijack_key]['monitor_keys']:
                    num_of_updates += 1
                    self.update_bgp_entries.add(
                        (hijack_key, bgp_entry_to_update))
                    # exclude handle bgp updates that point to same bgp as this hijack
                    self.handled_bgp_entries.discard(bgp_entry_to_update)

            if len(self.update_bgp_entries) > 0:
                try:
                    psycopg2.extras.execute_batch(
                        self.db_cur,
                        'UPDATE bgp_updates SET handled=true, hijack_key=%s WHERE key=%s ',
                        list(self.update_bgp_entries),
                        page_size=1000
                    )
                    self.db_conn.commit()
                except Exception:
                    log.exception('exception')
                    self.db_conn.rollback()
                    return -1

            num_of_updates += len(self.update_bgp_entries)
            self.update_bgp_entries.clear()

            # Update the BGP entries using the handled messages
            if len(self.handled_bgp_entries) > 0:
                try:
                    psycopg2.extras.execute_batch(
                        self.db_cur,
                        'UPDATE bgp_updates SET handled=true WHERE key=%s',
                        self.handled_bgp_entries,
                        page_size=1000
                    )
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

            try:
                cmd_ = 'INSERT INTO hijacks (key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, '
                cmd_ += 'time_started, time_last, time_ended, mitigation_started, time_detected, under_mitigation, '
                cmd_ += 'active, resolved, ignored, withdrawn, configured_prefix, timestamp_of_config, comment, peers_seen, peers_withdrawn, asns_inf) '
                cmd_ += 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) '
                cmd_ += 'ON CONFLICT(key, time_detected) DO UPDATE SET num_peers_seen=%s, num_asns_inf=%s, time_started=%s, '
                cmd_ += 'time_last=%s, peers_seen=%s, asns_inf=%s;'

                values = []
                for key in self.tmp_hijacks_dict:
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
                            self.tmp_hijacks_dict[key]['time_started']),  # time_started
                        datetime.datetime.fromtimestamp(
                            self.tmp_hijacks_dict[key]['time_last']),  # time_last
                        None,  # time_ended
                        None,  # mitigation_started
                        datetime.datetime.fromtimestamp(
                            self.tmp_hijacks_dict[key]['time_detected']),  # time_detected
                        False,  # under_mitigation
                        True,  # active
                        False,  # resolved
                        False,  # ignored
                        False, # withdrawn
                        # configured_prefix
                        self.tmp_hijacks_dict[key]['configured_prefix'],
                        datetime.datetime.fromtimestamp(
                            self.tmp_hijacks_dict[key]['timestamp_of_config']),  # timestamp_of_config
                        '',  # comment
                        self.tmp_hijacks_dict[key]['peers_seen'],  # peers_seen
                        [],  # peers_withdrawn
                        self.tmp_hijacks_dict[key]['asns_inf'],  # asns_inf
                        # num_peers_seen
                        self.tmp_hijacks_dict[key]['num_peers_seen'],
                        # num_asns_inf
                        self.tmp_hijacks_dict[key]['num_asns_inf'],
                        datetime.datetime.fromtimestamp(
                            self.tmp_hijacks_dict[key]['time_started']),  # time_started
                        datetime.datetime.fromtimestamp(
                            self.tmp_hijacks_dict[key]['time_last']),  # time_last
                        self.tmp_hijacks_dict[key]['peers_seen'],  # peers_seen
                        self.tmp_hijacks_dict[key]['asns_inf']  # asns_inf
                    )
                    values.append(values_)

                psycopg2.extras.execute_batch(self.db_cur, cmd_, values, page_size=1000)
                self.db_conn.commit()
            except Exception:
                log.exception('exception')
                self.db_conn.rollback()
                return -1

            num_of_entries = len(self.tmp_hijacks_dict)
            self.tmp_hijacks_dict.clear()
            return num_of_entries

        def _retrieve_unhandled(self, amount):
            results = []
            cmd_ = 'SELECT key, prefix, origin_as, peer_asn, as_path, service, '
            cmd_ += 'type, communities, timestamp FROM bgp_updates WHERE '
            cmd_ += 'handled = false ORDER BY timestamp DESC LIMIT(%s);'
            self.db_cur.execute(
                cmd_, (amount,))
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
                    'timestamp': entry[8].timestamp()
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
            inserts, updates, hijacks, withdrawals = self._insert_bgp_updates(
            ), self._update_bgp_updates(), self._insert_update_hijacks(
            ), self._handle_bgp_withdrawals()
            str_ = ''
            if inserts > 0:
                str_ += 'BGP Updates Inserted: {}\n'.format(inserts)
            if updates > 0:
                str_ += 'BGP Updates Updated: {}\n'.format(updates)
            if hijacks > 0:
                str_ += 'Hijacks Inserted: {}'.format(hijacks)
            if withdrawals > 0:
                str_ += 'Withdrawals Handled: {}'.format(withdrawals)
            if str_ != '':
                log.debug('{}'.format(str_))

        def _scheduler_instruction(self, message):
            msg_ = message.payload
            if msg_['op'] == 'bulk_operation':
                self._update_bulk()
            elif msg_['op'] == 'send_unhandled':
                self._retrieve_unhandled(msg_['amount'])
            else:
                log.warning(
                    'Received uknown instruction from scheduler: {}'.format(msg_))

        def _save_config(self, config_hash, yaml_config, raw_config):
            try:
                log.debug('Config Store..')
                cmd_ = 'INSERT INTO configs (key, config_data, raw_config, time_modified)'
                cmd_ += 'VALUES (%s, %s, %s, %s);'
                self.db_cur.execute(
                    cmd_,
                    (config_hash,
                     json.dumps(yaml_config),
                        raw_config,
                        datetime.datetime.now()))
                self.db_conn.commit()
            except Exception:
                log.exception('failed to save config in db')

        def _retrieve_most_recent_config_hash(self):
            try:
                self.db_cur.execute(
                    'SELECT key from configs ORDER BY time_modified DESC LIMIT 1')
                hash_ = self.db_cur.fetchone()
                if isinstance(hash_, tuple):
                    return hash_[0]
            except Exception:
                log.exception(
                    'failed to retrieved most recent config hash in db')
            return None


if __name__ == '__main__':
    service = Postgresql_db()
    service.run()
