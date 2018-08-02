import radix
import ipaddress
from profilehooks import profile
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
                routing_key='#')
        self.channel.basic_consume(self.handle_bgp_update,
                queue=self.bgp_update_queue,
                no_ack=True)

        self.prefix_tree = radix.Radix()
        self.flag = False
        self.rules = None

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

        self.init_detection()
        _thread.start_new_thread(self.channel.start_consuming, ())


    def handle_config_request_reply(self, channel, method, header, body):
        log.info(' [x] Detection - Received Configuration: {}'.format(body))
        if self.corr_id == header.correlation_id:
            raw = json.loads(body)
            self.rules = raw.get('rules', {})
            self.start()


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


