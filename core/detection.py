import radix
import ipaddress
from profilehooks import profile
from utils import log, exception_handler
import uuid
import pika
import json
import _thread


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

        # BGP Update Queue
        self.channel.exchange_declare(exchange='bgp_update',
                exchange_type='direct')
        result = self.channel.queue_declare(exclusive=True)
        self.bgp_update_queue = result.method.queue
        self.channel.queue_bind(exchange='bgp_update',
                queue=self.bgp_update_queue,
                routing_key='update')
        self.channel.basic_consume(self.handle_bgp_update,
                queue=self.bgp_update_queue,
                no_ack=True)

        self.prefix_tree = radix.Radix()
        self.flag = False
        self.rules = None

        self.future_memcache = {}

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

        _thread.start_new_thread(self.channel.start_consuming, ())


    def handle_config_request_reply(self, channel, method, header, body):
        log.info(' [x] Detection - Received Configuration: {}'.format(body))
        if self.corr_id == header.correlation_id:
            raw = json.loads(body)
            self.rules = raw.get('rules', {})
            self.init_detection()


    def __detection_generator(self, path_len, prefix_node):
        if prefix_node is not None:
            yield self.detect_squatting
            if path_len > 0:
                yield self.detect_origin_hijack
                if path_len > 1:
                    yield self.detect_type_1_hijack
                yield self.detect_subprefix_hijack

        yield self.mark_handled


    def init_detection(self):
        for rule in self.rules:
            for prefix in rule['prefixes']:
                node = self.prefix_tree.search_exact(prefix)
                if node is None:
                    node = self.prefix_tree.add(prefix)
                    node.data['confs'] = []

                conf_obj = {'origin_asns': rule['origin_asns'], 'neighbors': rule['neighbors']}
                node.data['confs'].append(conf_obj)

        log.debug('Detection configuration: {}'.format(self.rules))


    def handle_bgp_update(self, channel, method, header, body):
        log.info(' [x] Detection - Received BGP update: {}'.format(body))
        monitor_event = json.loads(body)

        monitor_event['as_path'] = ' '.join([str(c) for c in monitor_event['as_path']])

        log.debug('Hanlding monitor event: {}'.format(str(monitor_event)))

        # ignore withdrawals for now
        if monitor_event['type'] == 'W':
            self.mark_handled(monitor_event)
            return

        as_path = Detection.__clean_as_path(monitor_event['as_path'].split(' '))
        prefix_node = self.prefix_tree.search_best(monitor_event['prefix'])

        if prefix_node is not None:
            monitor_event['matched_prefix'] = prefix_node.prefix

        for func in self.__detection_generator(len(as_path), prefix_node):
            if func(monitor_event, prefix_node, as_path[-2]):
                break


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


    def commit_hijack(self, monitor_event, origin, hij_type):
        print('hijack {} {} {}'.format(monitor_event, origin, hij_type))
        pass


    def mark_handled(self, monitor_event):
        print('marked handled {}'.format(monitor_event))
        pass

