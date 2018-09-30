from kombu import Connection, uuid, Queue, Exchange, Consumer, Producer
from webapp.utils import RABBITMQ_HOST
from webapp.utils.conf import Config
import logging
import datetime

log = logging.getLogger('webapp_logger')

intervals = (
    ('W', 604800),  # 60 * 60 * 24 * 7
    ('D', 86400),    # 60 * 60 * 24
    ('H', 3600),    # 60 * 60
    ('M', 60),
    ('S', 1),
    )

def display_time(seconds, granularity=2):
    if seconds is None:
        return "N/A"
    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(int(value), name))
    return ', '.join(result[:granularity])

class Modules_status():

    def __init__(self):
        self.connection = None
        self.response = None
        self.init_conn()

    def init_conn(self):
        try:
            self.connection = Connection(RABBITMQ_HOST)
        except:
            log.error('Modules_status failed to connect to rabbitmq..')

    def call(self, module, action):
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'module': module,
                    'action': action
                    },
                exchange='',
                routing_key='controller-queue',
                declare=[callback_queue],
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
            )
        with Consumer(self.connection,
                      on_message=self.on_response,
                      queues=[callback_queue],
                      no_ack=True):
            while self.response is None:
                self.connection.drain_events()

    def is_up_or_running(self, module):
        log.debug(self.response)
        if 'response' in self.response:
            if 'status' in self.response['response']:
                if self.response['response']['status'] == 'up':
                    return True
            elif 'reason' in self.response['response']:
                if self.response['response']['reason'] == 'already running':
                    return True
        return False


    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def get_response_all(self):
        log.debug("payload: {}".format(self.response))
        ret_response = {}
        if 'response' in self.response:
            if self.response['response']['result'] == 'success':
                for module in ['configuration', 'scheduler', 'postgresql_db', 'monitor', 'detection', 'mitigation']:
                    ret_response[module] = {}
                    ret_response[module]['status'] = self.response['response'][module]['status']
                    ret_response[module]['uptime'] = display_time(self.response['response'][module].get('uptime', None))
        return ret_response

    def get_response_formmated_all(self):
        log.debug("payload: {}".format(self.response))
        ret_response = {}
        if 'response' in self.response:
            if self.response['response']['result'] == 'success':
                for module in [('configuration', 'Configuration'),
                            ('scheduler', 'Scheduler'),
                            ('postgresql_db', 'Postgresql'),
                            ('monitor', 'Monitor'),
                            ('detection', 'Detection'),
                            ('mitigation', 'Mitigation')]:
                    ret_response[module[1]] = {}
                    ret_response[module[1]]['status'] = self.response['response'][module[0]]['status']
                    ret_response[module[1]]['uptime'] = display_time(self.response['response'][module[0]].get('uptime', None))
        return ret_response








