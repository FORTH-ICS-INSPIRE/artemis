import radix
import ipaddress
from utils import exception_handler, RABBITMQ_HOST, MEMCACHED_HOST, TimedSet
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer
from kombu.mixins import ConsumerProducerMixin
import time
from pymemcache.client.base import Client
import pickle
import hashlib
import logging
from typing import Union, Dict, List, NoReturn, Callable, Tuple


log = logging.getLogger('artemis_logger')


def pickle_serializer(key: str, value: Union[str, Dict]) -> str:
    """
    Pickle Serializer for Memcached.
    """
    if isinstance(value, str):
        return value, 1
    return pickle.dumps(value), 2


def pickle_deserializer(key: str, value: str, flags: int) -> Union[str, Dict]:
    """
    Pickle Serializer for Memcached.
    """
    if flags == 1:
        return value
    if flags == 2:
        return pickle.loads(value)
    raise Exception('Unknown serialization format')


class Detection(Service):
    """
    Detection Service.
    """

    def run_worker(self) -> NoReturn:
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except BaseException:
            log.exception('exception')
        finally:
            log.info('stopped')

    class Worker(ConsumerProducerMixin):
        """
        RabbitMQ Consumer/Producer for this Service.
        """

        def __init__(self, connection: Connection) -> NoReturn:
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.monitors_seen = TimedSet()
            self.mon_num = 1

            self.memcache = Client((MEMCACHED_HOST, 11211),
                                   serializer=pickle_serializer,
                                   deserializer=pickle_deserializer)
            self.memcache.flush_all()

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

            # QUEUES
            self.update_queue = Queue('detection-update-update', exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                                      consumer_arguments={'x-priority': 1})
            self.update_unhandled_queue = Queue('detection-update-unhandled', exchange=self.update_exchange, routing_key='unhandled', durable=False, exclusive=True, max_priority=2,
                                                consumer_arguments={'x-priority': 2})
            self.hijack_resolved_queue = Queue('detection-hijack-resolved', exchange=self.hijack_exchange, routing_key='resolved', durable=False, exclusive=True, max_priority=2,
                                               consumer_arguments={'x-priority': 2})
            self.hijack_ignored_queue = Queue('detection-hijack-ignored', exchange=self.hijack_exchange, routing_key='ignored', durable=False, exclusive=True, max_priority=2,
                                              consumer_arguments={'x-priority': 2})
            self.hijack_fetch_queue = Queue('detection-hijack-fetch', exchange=self.hijack_exchange, routing_key='fetch', durable=False, exclusive=True, max_priority=2,
                                            consumer_arguments={'x-priority': 2})
            self.config_queue = Queue('detection-config-notify', exchange=self.config_exchange, routing_key='notify', durable=False, exclusive=True, max_priority=3,
                                      consumer_arguments={'x-priority': 3})

            self.config_request_rpc()

            self.producer.publish(
                '',
                exchange=self.hijack_exchange,
                routing_key='fetch-hijacks',
                priority=0
            )
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
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.update_unhandled_queue],
                    on_message=self.handle_unhandled_bgp_updates,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_fetch_queue],
                    on_message=self.fetch_ongoing_hijacks,
                    prefetch_count=1,
                    accept=['pickle'],
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_resolved_queue],
                    on_message=self.handle_resolved_or_ignored_hijack,
                    prefetch_count=1,
                    no_ack=True
                ),
                Consumer(
                    queues=[self.hijack_ignored_queue],
                    on_message=self.handle_resolved_or_ignored_hijack,
                    prefetch_count=1,
                    no_ack=True
                )
            ]

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

        def config_request_rpc(self) -> NoReturn:
            """
            Initial RPC of this service to request the configuration.
            The RPC is blocked until the configuration service replies back.
            """
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(), durable=False, max_priority=2,
                                   consumer_arguments={'x-priority': 2})

            self.producer.publish(
                '',
                exchange='',
                routing_key='config-request-queue',
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    callback_queue,
                    Queue(
                        'config-request-queue',
                        durable=False,
                        max_priority=2)],
                priority=2
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

        def handle_unhandled_bgp_updates(self, message: Dict) -> NoReturn:
            """
            Handles unhanlded bgp updates from the database in batches of 50.
            """
            # log.debug('{} unhandled events'.format(len(message.payload)))
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
                monitor_event = message.payload

            if monitor_event['key'] not in self.monitors_seen:
                raw = monitor_event.copy()
                # ignore withdrawals for now
                if monitor_event['type'] == 'A':
                    monitor_event['peer_asn'] = -1
                    if len(monitor_event['path']) > 1:
                        monitor_event['peer_asn'] = monitor_event['path'][0]
                    monitor_event['path'] = Detection.Worker.__clean_as_path(
                        monitor_event['path'])
                    prefix_node = self.prefix_tree.search_best(
                        monitor_event['prefix'])

                    if prefix_node is not None:
                        monitor_event['matched_prefix'] = prefix_node.prefix

                    try:
                        for func in self.__detection_generator(
                                len(monitor_event['path']), prefix_node):
                            if func(monitor_event, prefix_node):
                                break
                    except BaseException:
                        log.exception('exception')
                self.mark_handled(raw)
                self.mon_num += 1
            else:
                log.debug('already handled {}'.format(monitor_event['key']))

        def __detection_generator(self, path_len: int,
                                  prefix_node: radix.Radix) -> Callable:
            """
            Generator that returns detection functions based on rules and path length.
            Priority: Squatting > Subprefix > Origin > Type-1
            """
            if prefix_node is not None:
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
                    new_seq.append(int(x))

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
            # log.debug('before: {} / after: {}'.format(path, clean_as_path))
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
                if len(item['origin_asns']) > 0 or len(item['neighbors']) > 0:
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
            self.commit_hijack(monitor_event, origin_asn, 0)
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
                if origin_asn in item['origin_asns'] and first_neighbor_asn in item['neighbors']:
                    return False
            self.commit_hijack(monitor_event, first_neighbor_asn, 1)
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
                            if first_neighbor_asn in item['neighbors']:
                                false_first_neighbor = False
                            break
                    if origin_asn is not None and false_origin:
                        hijacker_asn = origin_asn
                    elif first_neighbor_asn is not None and false_first_neighbor:
                        hijacker_asn = first_neighbor_asn
                except BaseException:
                    log.exception(
                        'Problem in subprefix hijack detection, event {}'.format(monitor_event))
                self.commit_hijack(monitor_event, hijacker_asn, 'S')
                return True
            return False

        def commit_hijack(self, monitor_event: Dict,
                          hijacker: int, hij_type: str) -> NoReturn:
            """
            Commit new or update an existing hijack to the database.
            It uses memcache server to store ongoing hijacks information to not stress the db.
            """
            memcache_hijack_key = hashlib.md5(pickle.dumps(
                [monitor_event['prefix'], hijacker, hij_type])).hexdigest()
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

            if hij_type in {'S', 'Q'}:
                hijack_value['asns_inf'] = set(monitor_event['path'])
            else:
                hijack_value['asns_inf'] = set(
                    monitor_event['path'][:-(hij_type + 1)])

            result = self.memcache.get(memcache_hijack_key)
            if result is not None:
                result['time_started'] = min(
                    result['time_started'], hijack_value['time_started'])
                result['time_last'] = max(
                    result['time_last'], hijack_value['time_last'])
                result['peers_seen'].update(hijack_value['peers_seen'])
                result['asns_inf'].update(hijack_value['asns_inf'])
                # no update since db already knows!
                result['monitor_keys'] = hijack_value['monitor_keys']
            else:
                first_trigger = int(monitor_event['timestamp'])
                hijack_value['key'] = hashlib.md5(pickle.dumps(
                    [monitor_event['prefix'], hijacker, hij_type, first_trigger])).hexdigest()
                hijack_value['time_detected'] = time.time()
                result = hijack_value

            self.memcache.set(memcache_hijack_key, result)

            log.info('{}'.format(result))
            self.producer.publish(
                result,
                exchange=self.hijack_exchange,
                routing_key='update',
                serializer='pickle',
                priority=0
            )
            # log.debug('{}'.format(result))

        def mark_handled(self, monitor_event: Dict) -> NoReturn:
            """
            Marks a bgp update as handled on the database.
            """
            self.producer.publish(
                monitor_event['key'],
                exchange=self.handled_exchange,
                routing_key='update',
                priority=1
            )
            self.monitors_seen.add(monitor_event['key'])
            # log.debug('{}'.format(monitor_event['key']))

        def fetch_ongoing_hijacks(self, message: Dict) -> NoReturn:
            """
            Fetches ongoing hijacks from the database when the service starts.
            """
            # log.debug(
            #     'message: {}\npayload: {}'.format(
            #         message, message.payload))
            try:
                hijacks = message.payload
                for hijack_key, hijack_value in hijacks.items():
                    memcache_hijack_key = hashlib.md5(pickle.dumps([
                        hijack_value['prefix'],
                        hijack_value['hijack_as'],
                        hijack_value['type']])).hexdigest()
                    assert self.memcache.get(memcache_hijack_key) is None
                    self.memcache.set(memcache_hijack_key, hijack_value)
            except BaseException:
                log.exception(
                    "couldn't fetch data: {}".format(
                        message.payload))

        def handle_resolved_or_ignored_hijack(self, message: Dict) -> NoReturn:
            """
            Remove for memcache the ongoing hijack entry.
            """
            log.debug(
                'message: {}\npayload: {}'.format(
                    message, message.payload))
            try:
                data = message.payload
                memcache_hijack_key = hashlib.md5(pickle.dumps(
                    [data['prefix'], hijacker, hij_type])).hexdigest()
                self.memcache.delete(data['key'])
            except BaseException:
                log.exception(
                    "couldn't erase data: {}".format(
                        message.payload))
