import radix
import ipaddress
from profilehooks import profile
from utils import log, exception_handler, decorators
import hashlib
from multiprocessing import Process
from kombu import Connection, Queue, Exchange, uuid, Consumer, Producer
from kombu.mixins import ConsumerProducerMixin
import signal
import time
from setproctitle import setproctitle
import traceback


class Detection(Process):


    def __init__(self):
        super().__init__()
        self.worker = None
        self.stopping = False


    def run(self):
        setproctitle(self.name)
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        try:
            with Connection('amqp://guest:guest@localhost:5672//') as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            traceback.print_exc()
        self.stopping = True
        log.info('Detection Stopped..')


    def exit(self, signum, frame):
        if self.worker is not None:
            self.worker.should_stop = True
            while(self.stopping):
                time.sleep(1)


    class Worker(ConsumerProducerMixin):


        def __init__(self, connection):
            self.connection = connection

            self.h_num = 0
            self.j_num = 0

            self.flag = False
            self.rules = None
            self.prefix_tree = radix.Radix()

            self.future_memcache = {}


            # EXCHANGES
            self.control_exchange = Exchange('control', type='direct', durable=False, delivery_mode=1)
            self.update_exchange = Exchange('bgp_update', type='direct', durable=False, delivery_mode=1)
            self.hijack_exchange = Exchange('hijack_update', type='direct', durable=False, delivery_mode=1)
            self.handled_exchange = Exchange('handled_update', type='direct', durable=False, delivery_mode=1)


            # QUEUES
            self.callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
            self.control_queue = Queue('control_queue', exchange=self.control_exchange, routing_key='monitor', durable=False)
            self.update_queue = Queue('bgp_queue', exchange=self.update_exchange, routing_key='update', durable=False)
            self.hijack_queue = Queue('hijack_queue', exchange=self.hijack_exchange, routing_key='update', durable=False)
            self.handled_queue = Queue('handled_queue', exchange=self.hijack_exchange, routing_key='update', durable=False)

            self.config_request_rpc()
            self.init_detection()
            self.flag = True
            log.info('Detection Started..')


        def get_consumers(self, Consumer, channel):
            return [
                    Consumer(
                        queues=[self.control_queue],
                        on_message=self.handle_control,
                        prefetch_count=1,
                        no_ack=True),
                    Consumer(
                        queues=[self.update_queue],
                        on_message=self.handle_bgp_update,
                        prefetch_count=1,
                        no_ack=True)
                    ]


        def config_request_rpc(self):
            self.correlation_id = uuid()

            with Producer(self.connection) as producer:
                producer.publish(
                    '',
                    exchange='',
                    routing_key='config_request_queue',
                    reply_to=self.callback_queue.name,
                    correlation_id=self.correlation_id,
                    retry=True,
                    declare=[self.callback_queue, Queue('config_request_queue', durable=False)]
                )
            with Consumer(self.connection,
                        on_message=self.handle_config_request_reply,
                        queues=[self.callback_queue], no_ack=True):
                while self.rules is None:
                    self.connection.drain_events()


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


        def handle_config_request_reply(self, message):
            log.info(' [x] Detection - Received Configuration')
            if self.correlation_id == message.properties['correlation_id']:
                raw = message.payload
                self.rules = raw.get('rules', [])


        def handle_control(self, message):
            print(' [x] Detection - Handle Control {}'.format(message))
            getattr(self, message.payload)()


        def handle_bgp_update(self, message):
            # log.info(' [x] Detection - Received BGP update: {}'.format(message))
            monitor_event = message.payload
            # ignore withdrawals for now
            if monitor_event['type'] == 'A':
                monitor_event['path'] = Detection.Worker.__clean_as_path(monitor_event['path'])
                prefix_node = self.prefix_tree.search_best(monitor_event['prefix'])

                if prefix_node is not None:
                    monitor_event['matched_prefix'] = prefix_node.prefix

                try:
                    for func in self.__detection_generator(len(monitor_event['path']), prefix_node):
                        if func(monitor_event, prefix_node):
                            break
                except:
                    traceback.print_exc()
                    print(monitor_event)
            self.mark_handled(monitor_event)


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
            log.debug('__clean_as_path - before: {} / after: {}'.format(path, clean_as_path))
            return clean_as_path


        @exception_handler
        def detect_squatting(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if len(item['origin_asns']) > 0 or len(item['neighbors']) > 0:
                    return False
            self.commit_hijack(monitor_event, origin_asn, 'Q')
            return True


        @exception_handler
        def detect_origin_hijack(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            for item in prefix_node.data['confs']:
                if origin_asn in item['origin_asns']:
                    return False
            self.commit_hijack(monitor_event, origin_asn, 0)
            return True


        @exception_handler
        def detect_type_1_hijack(self, monitor_event, prefix_node, *args, **kwargs):
            origin_asn = monitor_event['path'][-1]
            first_neighbor_asn = monitor_event['path'][-2]
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
                'peers_seen': {monitor_event['peer_asn']},
            }

            if hij_type in {'S','Q'}:
                hijack_value['inf_asns'] = set(monitor_event['path'])
            else:
                hijack_value['inf_asns'] = set(monitor_event['path'][:-(hij_type+1)])

            if hijack_key in self.future_memcache:
                self.future_memcache[hijack_key]['time_started'] = min(self.future_memcache[hijack_key]['time_started'], hijack_value['time_started'])
                self.future_memcache[hijack_key]['time_last'] = max(self.future_memcache[hijack_key]['time_last'], hijack_value['time_last'])
                self.future_memcache[hijack_key]['peers_seen'].update(hijack_value['peers_seen'])
                self.future_memcache[hijack_key]['inf_asns'].update(hijack_value['inf_asns'])
            else:
                self.future_memcache[hijack_key] = hijack_value

            with Producer(self.connection) as producer:
                producer.publish(
                        self.future_memcache[hijack_key],
                        exchange=self.hijack_queue.exchange,
                        routing_key=self.hijack_queue.routing_key,
                        declare=[self.hijack_queue],
                        serializer='pickle'
                )
                log.info('Published Hijack #{}'.format(self.j_num))
                self.j_num += 1


        def mark_handled(self, monitor_event):
            with Producer(self.connection) as producer:
                producer.publish(
                        monitor_event,
                        exchange=self.handled_queue.exchange,
                        routing_key=self.handled_queue.routing_key,
                        declare=[self.handled_queue]
                )
                log.info('Published Handled #{}'.format(self.h_num))
                self.h_num += 1


