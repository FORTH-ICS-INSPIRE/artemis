from kombu import Connection, Exchange, Consumer, Producer, Queue, uuid
from webapp.utils import RABBITMQ_HOST
import difflib
import logging

log = logging.getLogger('webapp_logger')


class Resolve_hijack():

    def __init__(self, hijack_key, prefix, type_, hijack_as):
        self.connection = None
        self.hijack_key = hijack_key
        self.prefix = prefix
        self.type_ = type_
        self.hijack_as = hijack_as
        self.init_conn()
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('Resolve_hijack failed to connect to rabbitmq.')

    def resolve(self):
        log.debug(
            "send resolve hijack message with key: {}".format(
                self.hijack_key))
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                    'prefix': self.prefix,
                    'type': self.type_,
                    'hijack_as': self.hijack_as
                },
                exchange=self.hijack_exchange,
                routing_key='resolved',
                priority=2
            )


class Mitigate_hijack():

    def __init__(self, hijack_key, prefix):
        self.connection = None
        self.hijack_key = hijack_key
        self.prefix = prefix
        self.mitigation_exchange = Exchange(
            'mitigation', type='direct', durable=False, delivery_mode=1)
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('Resolve_hijack failed to connect to rabbitmq.')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def mitigate(self):
        log.debug("sending mitigate message")
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                    'prefix': self.prefix
                },
                exchange=self.mitigation_exchange,
                routing_key='mitigate',
                priority=2
            )


class Ignore_hijack():

    def __init__(self, hijack_key, prefix, type_, hijack_as):
        self.connection = None
        self.hijack_key = hijack_key
        self.prefix = prefix
        self.type_ = type_
        self.hijack_as = hijack_as
        self.init_conn()
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('Ignore_hijack failed to connect to rabbitmq.')

    def ignore(self):
        log.debug("sending ignore message")
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': self.hijack_key,
                    'prefix': self.prefix,
                    'type': self.type_,
                    'hijack_as': self.hijack_as
                },
                exchange=self.hijack_exchange,
                routing_key='ignored',
                priority=2
            )


class Comment_hijack():

    def __init__(self):
        self.connection = None
        self.init_conn()
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('Comment_hijack failed to connect to rabbitmq.')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_key, comment):
        log.debug("sending")
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(),
                               durable=False,
                               exclusive=True,
                               auto_delete=True,
                               max_priority=4,
                               consumer_arguments={
            'x-priority': 4})
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': hijack_key,
                    'comment': comment
                },
                exchange='',
                routing_key='db-hijack-comment',
                retry=True,
                declare=[callback_queue],
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                priority=4
            )
        with Consumer(self.connection,
                      on_message=self.on_response,
                      queues=[callback_queue],
                      no_ack=True):
            while self.response is None:
                self.connection.drain_events()
        if self.response['status'] == 'accepted':
            return 'Comment saved.', True
        return "Error while saving.", False


class Submit_new_config():

    def __init__(self):
        self.connection = None
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('New_config failed to connect to rabbitmq.')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def send(self, new_config, old_config, comment):

        changes = ''.join(difflib.unified_diff(new_config, old_config))
        if changes:
            self.response = None
            self.correlation_id = uuid()
            callback_queue = Queue(uuid(),
                                   durable=False,
                                   auto_delete=True,
                                   max_priority=4,
                                   consumer_arguments={
                'x-priority': 4})
            with Producer(self.connection) as producer:
                producer.publish(
                    {
                        'config': new_config,
                        'comment': comment
                    },
                    exchange='',
                    routing_key='config-modify-queue',
                    serializer='yaml',
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    priority=4
                )
            with Consumer(self.connection,
                          on_message=self.on_response,
                          queues=[callback_queue],
                          no_ack=True):
                while self.response is None:
                    self.connection.drain_events()

            if self.response['status'] == 'accepted':
                log.info('new configuration accepted:\n{}'.format(changes))
                return 'Configuration file updated.', True

            log.info('invalid configuration:\n{}'.format(new_config))
            return "Invalid configuration file.\n{}".format(
                self.response['reason']), False
        return "No changes found on the new configuration.", False


class Seen_hijack():

    def __init__(self):
        self.connection = None
        self.init_conn()
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception('Seen_hijack failed to connect to rabbitmq.')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_key, state):
        log.debug("sending")
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(),
                               durable=False,
                               exclusive=True,
                               auto_delete=True,
                               max_priority=4,
                               consumer_arguments={
            'x-priority': 4})
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'key': hijack_key,
                    'state': state
                },
                exchange='',
                routing_key='db-hijack-seen',
                retry=True,
                declare=[callback_queue],
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                priority=4
            )
        with Consumer(self.connection,
                      on_message=self.on_response,
                      queues=[callback_queue],
                      no_ack=True):
            while self.response is None:
                self.connection.drain_events()
        return self.response['status'] == 'accepted'


class Hijacks_multiple_action():

    def __init__(self):
        self.connection = None
        self.init_conn()
        self.hijack_exchange = Exchange(
            'hijack-update',
            type='direct',
            durable=False,
            delivery_mode=1)

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except BaseException:
            log.exception(
                'Hijacks_multiple_action failed to connect to rabbitmq.')

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_keys, action):
        log.debug("sending")
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(),
                               durable=False,
                               exclusive=True,
                               auto_delete=True,
                               max_priority=4,
                               consumer_arguments={
            'x-priority': 4})
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'keys': hijack_keys,
                    'action': action
                },
                exchange='',
                routing_key='db-hijack-multiple-action',
                retry=True,
                declare=[callback_queue],
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                priority=4
            )
        with Consumer(self.connection,
                      on_message=self.on_response,
                      queues=[callback_queue],
                      no_ack=True):
            while self.response is None:
                self.connection.drain_events()
        return self.response['status'] == 'accepted'
