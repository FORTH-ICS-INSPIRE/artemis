import radix
import ipaddress
from profilehooks import profile
from utils import log, exception_handler, decorators
import uuid
import pika
import pickle
import _thread
import hashlib
from utils.mq import AsyncConnection
import threading


class Detection(object):


    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        self.channel = self.connection.channel()

        # RPC Queue
        result = self.channel.queue_declare(exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(self.handle_config_request_reply,
                no_ack=True,
                queue=self.callback_queue)

        self.hijack_publisher = AsyncConnection(exchange='hijack_update',
                exchange_type='direct',
                routing_key='update',
                objtype='publisher')

        self.handled_publisher = AsyncConnection(exchange='handled_update',
                exchange_type='direct',
                routing_key='update',
                objtype='publisher')


        self.flag = False
        self.rules = None
        self.prefix_tree = radix.Radix()

        self.future_memcache = {}
        self.bgp_handler_consumer = self.handle_bgp_update()
        self.configuration_consumer = self.handle_config_notify()

        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(exchange='',
                                   routing_key='rpc_config_queue',
                                   properties=pika.BasicProperties(
                                         reply_to = self.callback_queue,
                                         correlation_id = self.corr_id,
                                         ),
                                   body='')

        while self.rules is None:
            self.connection.process_data_events()


    def start(self):
        if not self.flag:
            self.flag = True
            threading.Thread(target=self.configuration_consumer.run, args=()).start()
            threading.Thread(target=self.bgp_handler_consumer.run, args=()).start()
            threading.Thread(target=self.hijack_publisher.run, args=()).start()
            threading.Thread(target=self.handled_publisher.run, args=()).start()
            log.info('Detection Started..')


    def stop(self):
        if self.flag:
            self.bgp_handler_consumer.stop()
            self.hijack_publisher.stop()
            self.handled_publisher.stop()
            self.configuration_consumer.stop()
            self.flag = False
            log.info('Detection Stopped..')


    def handle_config_request_reply(self, channel, method, header, body):
        log.info(' [x] Detection - Received Configuration')
        if self.corr_id == header.correlation_id:
            raw = pickle.loads(body)
            self.rules = raw.get('rules', [])
            self.init_detection()


    @decorators.consumer_callback('config_notify', 'direct', 'notification')
    def handle_config_notify(self, channel, method, header, body):
        log.info(' [x] Detection - Received Configuration')
        raw = pickle.loads(body)
        self.rules = raw.get('rules', [])
        self.init_detection()


    def __detection_generator(self, path_len, prefix_node):
        if prefix_node is not None:
            yield self.detect_squatting
            if path_len > 0:
                yield self.detect_origin_hijack
                if path_len > 1:
                    yield self.detect_type_1_hijack
                yield self.detect_subprefix_hijack


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

        log.debug('Detection configuration: {}'.format(self.rules))


    @decorators.consumer_callback('bgp_update', 'direct', 'update')
    def handle_bgp_update(self, channel, method, header, body):
        print(self.rules)
        monitor_event = pickle.loads(body)
        log.info(' [x] Detection - Received BGP update: {}'.format(monitor_event))

        # ignore withdrawals for now
        if monitor_event['type'] == 'W':
            self.mark_handled(monitor_event)
            return

        as_path = Detection.__clean_as_path(monitor_event['as_path'])
        prefix_node = self.prefix_tree.search_best(monitor_event['prefix'])

        if prefix_node is not None:
            monitor_event['matched_prefix'] = prefix_node.prefix

        for func in self.__detection_generator(len(as_path), prefix_node):
            if func(monitor_event, prefix_node, as_path[-2]):
                break
        self.mark_handled(monitor_event)


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
    def __clean_as_path(as_path):
        (clean_as_path, is_loopy) = Detection.__remove_prepending(as_path)
        if is_loopy:
            clean_as_path = Detection.__clean_loops(clean_as_path)
        log.debug('__clean_as_path - before: {} / after: {}'.format(as_path, clean_as_path))
        return clean_as_path


    @exception_handler
    def detect_squatting(self, monitor_event, prefix_node, *args, **kwargs):
        origin_asn = int(monitor_event['as_path'][-1])
        for item in prefix_node.data['confs']:
            if len(item['origin_asns']) > 0 or len(item['neighbors']) > 0:
                return False
        self.commit_hijack(monitor_event, origin_asn, 'Q')
        return True


    @exception_handler
    def detect_origin_hijack(self, monitor_event, prefix_node, *args, **kwargs):
        origin_asn = int(monitor_event['as_path'][-1])
        for item in prefix_node.data['confs']:
            if origin_asn in item['origin_asns']:
                return False
        self.commit_hijack(monitor_event, origin_asn, 0)
        return True


    @exception_handler
    def detect_type_1_hijack(self, monitor_event, prefix_node, first_neighbor_asn, *args, **kwargs):
        origin_asn = int(monitor_event['as_path'][-1])
        for item in prefix_node.data['confs']:
            if origin_asn in item['origin_asns'] and first_neighbor_asn in item['neighbors']:
                return False
        self.commit_hijack(monitor_event, first_neighbor_asn, 1)
        return True


    @exception_handler
    def detect_subprefix_hijack(self, monitor_event, prefix_node, *args, **kwargs):
        mon_prefix = ipaddress.ip_network(monitor_event['prefix'])
        if prefix_node.prefixlen < mon_prefix.prefixlen:
            self.commit_hijack(monitor_event, -1, 'S')
            return True


    def commit_hijack(self, monitor_event, hijacker, hij_type):
        hijack_key = hash(frozenset([monitor_event['prefix'], hijacker, hij_type]))
        hijack_value = {
            'time_started': monitor_event['timestamp'],
            'time_last': monitor_event['timestamp'],
            'peers_seen': {monitor_event['as_path'][0]},
        }

        if hij_type in {'S','Q'}:
            hijack_value['inf_asns'] = set(monitor_event['as_path'])
        else:
            hijack_value['inf_asns'] = set(monitor_event['as_path'][:-(hij_type+1)])

        if hijack_key in self.future_memcache:
            self.future_memcache[hijack_key]['time_started'] = min(self.future_memcache[hijack_key]['time_started'], hijack_value['time_started'])
            self.future_memcache[hijack_key]['time_last'] = max(self.future_memcache[hijack_key]['time_last'], hijack_value['time_last'])
            self.future_memcache[hijack_key]['peers_seen'].update(hijack_value['peers_seen'])
            self.future_memcache[hijack_key]['inf_asns'].update(hijack_value['inf_asns'])
        else:
            self.future_memcache[hijack_key] = hijack_value

        self.hijack_publisher.publish_message(self.future_memcache[hijack_key])


    def mark_handled(self, monitor_event):
        self.handled_publisher.publish_message(monitor_event)


