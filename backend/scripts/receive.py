from __future__ import absolute_import, unicode_literals, print_function
from pprint import pformat
from kombu import Connection, Exchange, Queue, Consumer, eventloop
import os

#: By default messages sent to exchanges are persistent (delivery_mode=2),
#: and queues and exchanges are durable.
exchange = Exchange(
    'hijack-update',
    type='direct',
    durable=False,
    delivery_mode=1)
queue = Queue(
    'hijack-update-queue',
    exchange,
    routing_key='update',
    exclusive=True,
    durable=False,
    max_priority=1)


def pretty(obj):
    return pformat(obj, indent=4)


#: This is the callback applied when a message is received.
def handle_message(body, message):
    print('Received message: {0!r}'.format(body))
    print('  properties:\n{0}'.format(pretty(message.properties)))
    print('  delivery_info:\n{0}'.format(pretty(message.delivery_info)))


#: Create a connection and a channel.
#: If hostname, userid, password and virtual_host is not specified
#: the values below are the default, but listed here so it can
#: be easily changed.
with Connection(os.getenv('RABBITMQ_HOST', 'localhost')) as connection:

    #: Create consumer using our callback and queue.
    #: Second argument can also be a list to consume from
    #: any number of queues.
    with Consumer(connection, queue, callbacks=[handle_message], accept=['pickle']):

        #: Each iteration waits for a single event.  Note that this
        #: event may not be a message, or a message that is to be
        #: delivered to the consumers channel, but any event received
        #: on the connection.
        for _ in eventloop(connection):
            pass
