import logging
import pika
import pickle
from time import sleep

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger(__name__)


class AsyncConnection(object):


    def __init__(self, url='amqp://localhost:5672/', exchange='default', exchange_type='direct', routing_key='default', cb=None, objtype='consumer'):
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = url
        self._exchange = exchange
        self._exchange_type = exchange_type
        self._routing_key = routing_key
        self._type = objtype
        self._message_number = 0
        if cb is not None:
            self.on_message = cb

    def connect(self):
        LOGGER.info('Connecting to %s', self._url)
        return pika.SelectConnection(pika.URLParameters(self._url),
                                     self.on_connection_open,
                                     stop_ioloop_on_close=False)

    def on_connection_open(self, unused_connection):
        LOGGER.info('Connection opened')
        self.add_on_connection_close_callback()
        self.open_channel()

    def add_on_connection_close_callback(self):
        LOGGER.info('Adding connection close callback')
        self._connection.add_on_close_callback(self.on_connection_closed)

    def on_connection_closed(self, connection, reply_code, reply_text):
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            LOGGER.warning('Connection closed, reopening in 5 seconds: (%s) %s',
                            reply_code, reply_text)
            self._connection.add_timeout(5, self.reconnect)

    def reconnect(self):
        # This is the old connection IOLoop instance, stop its ioloop
        self._connection.ioloop.stop()
        if not self._closing:
            # Create a new connection
            self._connection = self.connect()
            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()

    def open_channel(self):
        LOGGER.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        LOGGER.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self._exchange)

    def add_on_channel_close_callback(self):
        LOGGER.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, code, text):
        LOGGER.warning('Channel %i was closed: %s', channel, text)
        self._connection.close()

    def setup_exchange(self, exchange_name):
        LOGGER.info('Declaring exchange %s', exchange_name)
        self._channel.exchange_declare(self.on_exchange_declareok,
                                       exchange_name,
                                       self._exchange_type)

    def on_exchange_declareok(self, unused_frame):
        LOGGER.info('Exchange declared')

        if self._type == 'consumer':
            self.setup_queue()

    def setup_queue(self):
        self._channel.queue_declare(self.on_queue_declareok)

    def on_queue_declareok(self, method_frame):
        self._queue = method_frame.method.queue
        LOGGER.info('Binding %s to %s with %s',
                    self._exchange, self._queue, self._routing_key)
        self._channel.queue_bind(self.on_bindok, self._queue,
                                 self._exchange, self._routing_key)

    def on_bindok(self, unused_frame):
        LOGGER.info('Queue bound')

        self.start_consuming()

    def start_consuming(self):
        LOGGER.info('Issuing consumer related commands')
        self._consumer_tag = self._channel.basic_consume(
                self.on_message,
                queue=self._queue,
                no_ack=True)

    def on_message(self, unused_channel, basic_deliver, properties, body):
        LOGGER.info('Received message # %s from %s: %s',
                    basic_deliver.delivery_tag, properties.app_id, body)

    def publish_message(self, message):
        while self._channel is None or not self._channel.is_open:
            time.sleep(1)

        self._channel.basic_publish(self._exchange,
                self._routing_key,
                pickle.dumps(message))
        self._message_number += 1
        LOGGER.info('Published message # %i', self._message_number)

    def close_channel(self):
        LOGGER.info('Closing the channel')
        self._channel.close()

    def run(self):
        self._connection = self.connect()
        self._connection.ioloop.start()

    def stop(self):
        LOGGER.info('Stopping')
        self._closing = True

        self.close_channel()
        self.close_connection()
        self._connection.ioloop.start()
        LOGGER.info('Stopped')

    def close_connection(self):
        LOGGER.info('Closing connection')
        self._connection.close()
