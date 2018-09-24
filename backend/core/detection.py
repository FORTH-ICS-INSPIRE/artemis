import radix
import ipaddress
from utils import get_logger, exception_handler, RABBITMQ_HOST, MEMCACHED_HOST, TimedSet
from utils.service import Service
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import time
from pymemcache.client.base import Client
import pickle
import hashlib


log = get_logger(__name__)

def pickle_serializer(key, value):
     if type(value) == str:
         return value, 1
     return pickle.dumps(value), 2


def pickle_deserializer(key, value, flags):
    if flags == 1:
        return value
    if flags == 2:
        return pickle.loads(value)
    raise Exception('Unknown serialization format')

class Detection(Service):


    def run_worker(self):
        try:
            with Connection(RABBITMQ_HOST) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except:
            log.exception('exception')
        finally:
            log.info('stopped')


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection
            self.timestamp = -1
            self.rules = None
            self.prefix_tree = None
            self.monitors_seen = TimedSet()
            self.mon_num = 1

            self.memcache = Client((MEMCACHED_HOST, 11211),
                    serializer=pickle_serializer,
                    deserializer=pickle_deserializer)


            # EXCHANGES
            self.update_exchange = Exchange('bgp-update', channel=connection, type='direct', auto_delete=True, durable=False, delivery_mode=1)
            self.hijack_exchange = Exchange('hijack-update', channel=connection, type='direct', auto_delete=True, durable=False, delivery_mode=1)
            self.hijack_exchange.declare()
            self.handled_exchange = Exchange('handled-update', channel=connection, type='direct', auto_delete=True, durable=False, delivery_mode=1)
            self.handled_exchnage.declare()
            self.config_exchange = Exchange('config', channel=connection, type='direct', auto_delete=True, durable=False, delivery_mode=1)


            # QUEUES
            self.update_queue = Queue('detection-update-update', exchange=self.update_exchange, routing_key='update', durable=False, exclusive=True, max_priority=1,
                    consumer_arguments={'x-priority': 1})
            self.update_unhandled_queue = Queue('detection-update-unhandled', exchange=self.update_exchange, routing_key='unhandled', durable=False, exclusive=True, max_priority=2,
                    consumer_arguments={'x-priority': 2})
            self.hijack_resolved_queue = Queue('detection-hijack-resolved', exchange=self.hijack_exchange, routing_key='resolved', durable=False, exclusive=True, max_priority=2,
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
                        queues=[self.update_unhandled_queue],
                        on_message=self.handle_unhandled_bgp_updates,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    Consumer(
                        queues=[self.hijack_fetch_queue],
                        on_message=self.fetch_ongoing_hijacks,
                        prefetch_count=1,
                        no_ack=True
                        ),
                    Consumer(
                        queues=[self.hijack_resolved_queue],
                        on_message=self.handle_resolved_hijack,
                        prefetch_count=1,
                        no_ack=True
                        )
                    ]


        def handle_config_notify(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            raw = message.payload
            if raw['timestamp'] > self.timestamp:
                self.timestamp = raw['timestamp']
                self.rules = raw.get('rules', [])
                self.init_detection()


        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(), durable=False, max_priority=2,
                    consumer_arguments={'x-priority': 2})

            self.producer.publish(
                '',
                exchange = '',
                routing_key = 'config-request-queue',
                reply_to = callback_queue.name,
                correlation_id = self.correlation_id,
                retry = True,
                declare = [callback_queue, Queue('config-request-queue', durable=False, max_priority=2)],
                priority = 2
            )
            with Consumer(self.connection,
                        on_message=self.handle_config_request_reply,
                        queues=[callback_queue],
                        no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()
            log.debug('{}'.format(self.rules))


        def handle_config_request_reply(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                if raw['timestamp'] > self.timestamp:
                    self.timestamp = raw['timestamp']
                    self.rules = raw.get('rules', [])
                    self.init_detection()


        def init_detection(self):
            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                for prefix in rule['prefixes']:
                    node = self.prefix_tree.search_exact(prefix)
                    if node is None:
                        node = self.prefix_tree.add(prefix)
                        node.data['confs'] = []

                    conf_obj = {'origin_asns': rule['origin_asns'], 'neighbors': rule['neighbors']}
                    node.data['confs'].append(conf_obj)


        def handle_unhandled_bgp_updates(self, message):
            log.info('{} unhandled events'.format(len(message.payload)))
            for update in message.payload:
                self.handle_bgp_update(update)


        def handle_bgp_update(self, message):
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
                    monitor_event['path'] = Detection.Worker.__clean_as_path(monitor_event['path'])
                    prefix_node = self.prefix_tree.search_best(monitor_event['prefix'])


                    if prefix_node is not None:
                        monitor_event['matched_prefix'] = prefix_node.prefix

                    try:
                        for func in self.__detection_generator(len(monitor_event['path']), prefix_node):
                            if func(monitor_event, prefix_node):
                                break
                    except:
                        log.exception('exception')
                self.mark_handled(raw)
                self.mon_num += 1
            else:
                log.debug('already handled {}'.format(monitor_event['key']))


        def __detection_generator(self, path_len, prefix_node):
            if prefix_node is not None:
                yield self.detect_squatting
                if path_len > 0:
                    yield self.detect_origin_hijack
                    if path_len > 1:
                        yield self.detect_type_1_hijack
                    yield self.detect_subprefix_hijack


        @staticmethod
        def __remove_prepending(seq):
            last_add = None
            new_seq = []
            for x in seq:
                if last_add != x:
                    last_add = x
                    new_seq.append(int(x))

            is_loopy = False
            if len(set(seq)) != len(new_seq):
                is_loopy = True
                #raise Exception('Routing Loop: {}'.format(seq))
            return (new_seq, is_loopy)


        @staticmethod
        def __clean_loops(seq):
            # use inverse direction to clean loops in the path of the traffic
            seq_inv = seq[::-1]
            new_seq_inv = []
            for x in seq_inv:
                if x not in new_seq_inv:
                    new_seq_inv.append(x)
                else:
                    x_index = new_seq_inv.index(x)
                    new_seq_inv = new_seq_inv[:x_index+1]
            return new_seq_inv[::-1]


        @staticmethod
        def __clean_as_path(path):
            (clean_as_path, is_loopy) = Detection.Worker.__remove_prepending(path)
            if is_loopy:
                clean_as_path = Detection.Worker.__clean_loops(clean_as_path)
            # log.debug('before: {} / after: {}'.format(path, clean_as_path))
            return clean_as_path


        @exception_handler(log)
        def detect_squatting(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if len(item['origin_asns']) > 0 or len(item['neighbors']) > 0:
                    return False
            self.commit_hijack(monitor_event, origin_asn, 'Q')
            return True


        @exception_handler(log)
        def detect_origin_hijack(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if origin_asn in item['origin_asns']:
                    return False
            self.commit_hijack(monitor_event, origin_asn, 0)
            return True


        @exception_handler(log)
        def detect_type_1_hijack(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            first_neighbor_asn = monitor_event['path'][-2]
            for item in prefix_node.data['confs']:
                if origin_asn in item['origin_asns'] and first_neighbor_asn in item['neighbors']:
                    return False
            self.commit_hijack(monitor_event, first_neighbor_asn, 1)
            return True


        @exception_handler(log)
        def detect_subprefix_hijack(self, monitor_event, prefix_node, *args, **kwargs):
            mon_prefix = ipaddress.ip_network(monitor_event['prefix'])
            if prefix_node.prefixlen < mon_prefix.prefixlen:
                self.commit_hijack(monitor_event, -1, 'S')
                return True


        def commit_hijack(self, monitor_event, hijacker, hij_type):
            future_memcache_hijack_key = hashlib.md5(pickle.dumps([monitor_event['prefix'], hijacker, hij_type])).hexdigest()
            hijack_value = {
                'prefix': monitor_event['prefix'],
                'hijacker': hijacker,
                'hij_type': hij_type,
                'time_started': monitor_event['timestamp'],
                'time_last': monitor_event['timestamp'],
                'peers_seen': {monitor_event['peer_asn']},
                'monitor_keys': {monitor_event['key']}
            }

            if hij_type in {'S','Q'}:
                hijack_value['inf_asns'] = set(monitor_event['path'])
            else:
                hijack_value['inf_asns'] = set(monitor_event['path'][:-(hij_type+1)])

            result = self.memcache.get(future_memcache_hijack_key)
            if result is not None:
                result['time_started'] = min(result['time_started'], hijack_value['time_started'])
                result['time_last'] = max(result['time_last'], hijack_value['time_last'])
                result['peers_seen'].update(hijack_value['peers_seen'])
                result['inf_asns'].update(hijack_value['inf_asns'])
                result['monitor_keys'] = hijack_value['monitor_keys'] # no update since db already knows!
            else:
                first_trigger = monitor_event['timestamp']
                hijack_value['key'] = hashlib.md5(pickle.dumps([monitor_event['prefix'], hijacker, hij_type, first_trigger])).hexdigest()
                result = hijack_value

            self.memcache.set(future_memcache_hijack_key, result)

            self.producer.publish(
                    result,
                    exchange=self.hijack_exchange,
                    routing_key='update',
                    serializer='pickle',
                    priority=0
            )
            log.info('{}'.format(result))


        def mark_handled(self, monitor_event):
            self.producer.publish(
                    monitor_event['key'],
                    exchange=self.handled_exchange,
                    routing_key='update',
                    priority=1
            )
            self.monitors_seen.add(monitor_event['key'])
            log.info('{}'.format(monitor_event['key']))


        def fetch_ongoing_hijacks(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            hijacks = message.payload
            self.memcache.set_many(hijacks)


        def handle_resolved_hijack(self, message):
            log.info('message: {}\npayload: {}'.format(message, message.payload))
            self.memcache.delete(message.payload)


