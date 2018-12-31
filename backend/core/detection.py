import radix
import re
import ipaddress
from utils import exception_handler, RABBITMQ_HOST, get_logger, redis_key, purge_redis_eph_pers_keys
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
import pickle
import hashlib
import logging
from typing import Dict, List, NoReturn, Callable, Tuple
import redis
import json
from datetime import datetime


log = get_logger()
hij_log = logging.getLogger('hijack_logger')
mail_log = logging.getLogger('mail_logger')


class Detection():

    """
    Detection Service.
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
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.mon_num = 1

            self.redis = redis.Redis(
                host='localhost',
                port=6379
            )

            # EXCHANGES
            self.update_exchange = Exchange(
                'bgp-update',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.hijack_exchange = Exchange(
                'hijack-update',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.hijack_exchange.declare()
            self.handled_exchange = Exchange(
                'handled-update',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.handled_exchange.declare()
            self.config_exchange = Exchange(
                'config',
                channel=connection,
                type='direct',
                durable=False,
                delivery_mode=1)
            self.pg_amq_bridge = Exchange(
                'amq.direct',
                type='direct',
                durable=True,
                delivery_mode=1)

            # QUEUES
            self.update_queue = Queue(
                'detection-update-update', exchange=self.pg_amq_bridge, routing_key='update-insert', durable=False, auto_delete=True, max_priority=1,
                consumer_arguments={'x-priority': 1})
            self.update_unhandled_queue = Queue(
                'detection-update-unhandled', exchange=self.update_exchange, routing_key='unhandled', durable=False, auto_delete=True, max_priority=2,
                consumer_arguments={'x-priority': 2})
            self.hijack_ongoing_queue = Queue(
                'detection-hijack-ongoing', exchange=self.hijack_exchange, routing_key='ongoing', durable=False, auto_delete=True, max_priority=1,
                consumer_arguments={'x-priority': 1})
            self.config_queue = Queue(
                'detection-config-notify-{}'.format(uuid()), exchange=self.config_exchange, routing_key='notify', durable=False, auto_delete=True, max_priority=3,
                consumer_arguments={'x-priority': 3})
            self.update_rekey_queue = Queue(
                'detection-update-rekey', exchange=self.update_exchange, routing_key='hijack-rekey', durable=False, auto_delete=True, max_priority=1,
                consumer_arguments={'x-priority': 1})

            self.config_request_rpc()

            log.info('started')

        def get_consumers(self, Consumer: Consumer,
                          channel: Connection) -> List[Consumer]:
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
                    queues=[self.update_unhandled_queue],
                    on_message=self.handle_unhandled_bgp_updates,
                    prefetch_count=1000,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_ongoing_queue],
                    on_message=self.handle_ongoing_hijacks,
                    prefetch_count=10,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.update_rekey_queue],
                    on_message=self.handle_rekey_update,
                    prefetch_count=10,
                    no_ack=True
                )
            ]

        def on_consume_ready(self, connection, channel, consumers, **kwargs):
            self.producer.publish(
                self.timestamp,
                exchange=self.hijack_exchange,
                routing_key='ongoing-request',
                priority=1
            )

        def handle_config_notify(self, message: Dict) -> NoReturn:
            """
            Consumer for Config-Notify messages that come from the configuration service.
            Upon arrival this service updates its running configuration.
            """
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.init_detection()
                # Request ongoing hijacks from DB
                self.producer.publish(
                    self.timestamp,
                    exchange=self.hijack_exchange,
                    routing_key='ongoing-request',
                    priority=1
                )

        def config_request_rpc(self) -> NoReturn:
            """
            Initial RPC of this service to request the configuration.
            The RPC is blocked until the configuration service replies back.
            """
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
            log.debug('{}'.format(self.rules))

        def handle_config_request_reply(self, message: Dict):
            """
            Callback function for the config request RPC.
            Updates running configuration upon receiving a new configuration.
            """
            log.info(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                if raw['timestamp'] > self.timestamp:
                    self.timestamp = raw['timestamp']
                    self.rules = raw.get('rules', [])
                    self.init_detection()

        def init_detection(self) -> NoReturn:
            """
            Updates rules everytime it receives a new configuration.
            """
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

        def handle_ongoing_hijacks(self, message: Dict) -> NoReturn:
            """
            Handles ongoing hijacks from the database.
            """
            # log.debug('{} ongoing hijack events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_unhandled_bgp_updates(self, message: Dict) -> NoReturn:
            """
            Handles unhanlded bgp updates from the database in batches of 50.
            """
            # log.debug('{} unhandled events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_rekey_update(self, message: Dict) -> NoReturn:
            """
            Handles BGP updates, needing hijack rekeying from the database.
            """
            # log.debug('{} rekeying events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)

        def handle_bgp_update(self, message: Dict) -> NoReturn:
            """
            Callback function that runs the main logic of detecting hijacks for every bgp update.
            """
            # log.debug('{}'.format(message))
            if isinstance(message, dict):
                monitor_event = message
            else:
                monitor_event = json.loads(message.payload)
                monitor_event['path'] = monitor_event['as_path']
                monitor_event['timestamp'] = datetime(
                    *map(int, re.findall('\d+', monitor_event['timestamp']))).timestamp()

            if not self.redis.exists(
                    monitor_event['key']) or 'hij_key' in monitor_event:
                raw = monitor_event.copy()

                # mark the initial redis hijack key since it may change upon
                # outdated checks
                if 'hij_key' in monitor_event:
                    monitor_event['initial_redis_hijack_key'] = redis_key(
                        monitor_event['prefix'],
                        monitor_event['hijack_as'],
                        monitor_event['hij_type']
                    )

                is_hijack = False
                # ignore withdrawals for now
                if monitor_event['type'] == 'A':
                    monitor_event['path'] = Detection.Worker.__clean_as_path(
                        monitor_event['path'])
                    prefix_node = self.prefix_tree.search_best(
                        monitor_event['prefix'])

                    if prefix_node is not None:
                        monitor_event['matched_prefix'] = prefix_node.prefix

                        try:
                            for func in self.__detection_generator(
                                    len(monitor_event['path'])):
                                if func(monitor_event, prefix_node):
                                    is_hijack = True
                                    break
                        except Exception:
                            log.exception('exception')

                    if ((not is_hijack and 'hij_key' in monitor_event) or
                        (is_hijack and 'hij_key' in monitor_event and
                            monitor_event['initial_redis_hijack_key'] != monitor_event['final_redis_hijack_key'])):
                        redis_hijack_key = redis_key(
                            monitor_event['prefix'],
                            monitor_event['hijack_as'],
                            monitor_event['hij_type'])
                        purge_redis_eph_pers_keys(
                            self.redis, redis_hijack_key, monitor_event['hij_key'])
                        self.mark_outdated(
                            monitor_event['hij_key'], redis_hijack_key)
                    elif not is_hijack:
                        self.mark_handled(raw)

                elif monitor_event['type'] == 'W':
                    self.producer.publish(
                        {
                            'prefix': monitor_event['prefix'],
                            'peer_asn': monitor_event['peer_asn'],
                            'timestamp': monitor_event['timestamp'],
                            'key': monitor_event['key']
                        },
                        exchange=self.update_exchange,
                        routing_key='withdraw',
                        priority=0
                    )

                self.redis.set(monitor_event['key'], '', ex=60 * 60)
            else:
                log.debug('already handled {}'.format(monitor_event['key']))

        def __detection_generator(self, path_len: int) -> Callable:
            """
            Generator that returns detection functions based on rules and path length.
            Priority: Squatting > Subprefix > Origin > Type-1
            """
            yield self.detect_squatting
            yield self.detect_subprefix_hijack
            if path_len > 0:
                yield self.detect_origin_hijack
                if path_len > 1:
                    yield self.detect_type_1_hijack

        @staticmethod
        def __remove_prepending(seq: List[int]) -> Tuple[List[int], bool]:
            """
            Static method to remove prepending ASs from AS path.
            """
            last_add = None
            new_seq = []
            for x in seq:
                if last_add != x:
                    last_add = x
                    new_seq.append(x)

            is_loopy = False
            if len(set(seq)) != len(new_seq):
                is_loopy = True
                # raise Exception('Routing Loop: {}'.format(seq))
            return (new_seq, is_loopy)

        @staticmethod
        def __clean_loops(seq: List[int]) -> List[int]:
            """
            Static method that remove loops from AS path.
            """
            # use inverse direction to clean loops in the path of the traffic
            seq_inv = seq[::-1]
            new_seq_inv = []
            for x in seq_inv:
                if x not in new_seq_inv:
                    new_seq_inv.append(x)
                else:
                    x_index = new_seq_inv.index(x)
                    new_seq_inv = new_seq_inv[:x_index + 1]
            return new_seq_inv[::-1]

        @staticmethod
        def __clean_as_path(path: List[int]) -> List[int]:
            """
            Static wrapper method for loop and prepending removal.
            """
            (clean_as_path, is_loopy) = Detection.Worker.__remove_prepending(path)
            if is_loopy:
                clean_as_path = Detection.Worker.__clean_loops(clean_as_path)
            return clean_as_path

        @exception_handler(log)
        def detect_squatting(
                self, monitor_event: Dict,
                prefix_node: radix.Radix, *args, **kwargs) -> bool:
            """
            Squatting detection.
            """
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if len(item['origin_asns']) > 0:
                    return False
            self.commit_hijack(monitor_event, origin_asn, 'Q')
            return True

        @exception_handler(log)
        def detect_origin_hijack(
                self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs) -> bool:
            """
            Origin hijack detection.
            """
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if origin_asn in item['origin_asns']:
                    return False
            self.commit_hijack(monitor_event, origin_asn, '0')
            return True

        @exception_handler(log)
        def detect_type_1_hijack(
                self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs) -> bool:
            """
            Type-1 hijack detection.
            """
            origin_asn = monitor_event['path'][-1]
            first_neighbor_asn = monitor_event['path'][-2]
            for item in prefix_node.data['confs']:
                # [] neighbors means "allow everything"
                if origin_asn in item['origin_asns'] and (
                        len(item['neighbors']) == 0 or first_neighbor_asn in item['neighbors']):
                    return False
            self.commit_hijack(monitor_event, first_neighbor_asn, '1')
            return True

        @exception_handler(log)
        def detect_subprefix_hijack(
                self, monitor_event: Dict, prefix_node: radix.Radix, *args, **kwargs) -> bool:
            """
            Subprefix hijack detection.
            """
            mon_prefix = ipaddress.ip_network(monitor_event['prefix'])
            if prefix_node.prefixlen < mon_prefix.prefixlen:
                hijacker_asn = -1
                try:
                    origin_asn = None
                    first_neighbor_asn = None
                    if len(monitor_event['path']) > 0:
                        origin_asn = monitor_event['path'][-1]
                    if len(monitor_event['path']) > 1:
                        first_neighbor_asn = monitor_event['path'][-2]
                    false_origin = True
                    false_first_neighbor = True
                    for item in prefix_node.data['confs']:
                        if origin_asn in item['origin_asns']:
                            false_origin = False
                            if first_neighbor_asn in item['neighbors'] or len(
                                    item['neighbors']) == 0:
                                false_first_neighbor = False
                            break
                    if origin_asn is not None and false_origin:
                        hijacker_asn = origin_asn
                    elif first_neighbor_asn is not None and false_first_neighbor:
                        hijacker_asn = first_neighbor_asn
                except Exception:
                    log.exception(
                        'Problem in subprefix hijack detection, event {}'.format(monitor_event))
                self.commit_hijack(monitor_event, hijacker_asn, 'S')
                return True
            return False

        def commit_hijack(self, monitor_event: Dict,
                          hijacker: int, hij_type: str) -> NoReturn:
            """
            Commit new or update an existing hijack to the database.
            It uses redis server to store ongoing hijacks information to not stress the db.
            """
            redis_hijack_key = redis_key(
                monitor_event['prefix'],
                hijacker,
                hij_type)

            if 'hij_key' in monitor_event:
                monitor_event['final_redis_hijack_key'] = redis_hijack_key
                return

            hijack_value = {
                'prefix': monitor_event['prefix'],
                'hijack_as': hijacker,
                'type': hij_type,
                'time_started': monitor_event['timestamp'],
                'time_last': monitor_event['timestamp'],
                'peers_seen': {monitor_event['peer_asn']},
                'monitor_keys': {monitor_event['key']},
                'configured_prefix': monitor_event['matched_prefix'],
                'timestamp_of_config': self.timestamp
            }

            hijack_value['asns_inf'] = set()
            # for squatting, all ASes except the origin are considered infected
            if hij_type == 'Q':
                if len(monitor_event['path']) > 0:
                    hijack_value['asns_inf'] = set(monitor_event['path'][:-1])
            # for sub-prefix hijacks, the infection depends on whether the
            # hijacker is the origin/neighbor/sth else
            elif hij_type == 'S':
                if len(monitor_event['path']) > 1:
                    if hijacker == monitor_event['path'][-1]:
                        hijack_value['asns_inf'] = set(
                            monitor_event['path'][:-1])
                    elif hijacker == monitor_event['path'][-2]:
                        hijack_value['asns_inf'] = set(
                            monitor_event['path'][:-2])
                    else:
                        # assume the hijacker does a Type-2
                        if len(monitor_event['path']) > 2:
                            hijack_value['asns_inf'] = set(
                                monitor_event['path'][:-3])
            # for exact-prefix type-0/type-1 hijacks, the pollution depends on
            # the type
            else:
                hijack_value['asns_inf'] = set(
                    monitor_event['path'][:-(int(hij_type) + 1)])

            # make the following operation atomic using blpop (blocking)
            # first, make sure that the semaphore is initialized
            if self.redis.getset('{}token_active'.format(
                    redis_hijack_key), 1) != b'1':
                redis_pipeline = self.redis.pipeline()
                redis_pipeline.lpush(
                    '{}token'.format(redis_hijack_key), 'token')
                # lock, by extracting the token (other processes that access it at the same time will be blocked)
                # attention: it is important that this command is batched in the pipeline since the db may async delete
                # the token
                redis_pipeline.blpop('{}token'.format(redis_hijack_key))
                redis_pipeline.execute()
            else:
                # lock, by extracting the token (other processes that access it
                # at the same time will be blocked)
                self.redis.blpop('{}token'.format(redis_hijack_key))

            # proceed now that we have clearance
            redis_pipeline = self.redis.pipeline()
            try:
                result = self.redis.get(redis_hijack_key)
                if result is not None:
                    result = pickle.loads(result)
                    result['time_started'] = min(
                        result['time_started'], hijack_value['time_started'])
                    result['time_last'] = max(
                        result['time_last'], hijack_value['time_last'])
                    result['peers_seen'].update(hijack_value['peers_seen'])
                    result['asns_inf'].update(hijack_value['asns_inf'])
                    # no update since db already knows!
                    result['monitor_keys'] = hijack_value['monitor_keys']
                else:
                    hijack_value['time_detected'] = time.time()
                    hijack_value['key'] = hashlib.md5(pickle.dumps(
                        [monitor_event['prefix'], hijacker, hij_type, hijack_value['time_detected']])).hexdigest()
                    redis_pipeline.sadd('persistent-keys', hijack_value['key'])
                    result = hijack_value
                    mail_log.info('{}'.format(result))
                redis_pipeline.set(redis_hijack_key, pickle.dumps(result))
            except Exception:
                log.exception('exception')
            finally:
                # unlock, by pushing back the token (at most one other process
                # waiting will be unlocked)
                redis_pipeline.set(
                    '{}token_active'.format(redis_hijack_key), 1)
                redis_pipeline.lpush(
                    '{}token'.format(redis_hijack_key), 'token')
                redis_pipeline.execute()

            self.producer.publish(
                result,
                exchange=self.hijack_exchange,
                routing_key='update',
                serializer='pickle',
                priority=0
            )
            hij_log.info('{}'.format(result))

        def mark_handled(self, monitor_event: Dict) -> NoReturn:
            """
            Marks a bgp update as handled on the database.
            """
            # log.debug('{}'.format(monitor_event['key']))
            self.producer.publish(
                monitor_event['key'],
                exchange=self.handled_exchange,
                routing_key='update',
                priority=1
            )

        def mark_outdated(self, hij_key: str, redis_hij_key: str) -> NoReturn:
            """
            Marks a hijack as outdated on the database.
            """
            # log.debug('{}'.format(hij_key))
            msg = {
                'persistent_hijack_key': hij_key,
                'redis_hijack_key': redis_hij_key
            }
            self.producer.publish(
                msg,
                exchange=self.hijack_exchange,
                routing_key='outdate',
                priority=1
            )


def run():
    service = Detection()
    service.run()


if __name__ == '__main__':
    run()
