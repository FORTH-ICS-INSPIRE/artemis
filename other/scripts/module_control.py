#!/usr/bin/env python
import sys
import time
import os
from kombu import Connection, Producer, Consumer, Queue, uuid
import traceback
import argparse


class ControllerCLI(object):

    def __init__(self, connection):
        self.connection = connection

    def on_response(self, message):
        if message.properties['correlation_id'] == self.correlation_id:
            self.response = message.payload

    def call(self, module, action):
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(uuid(), exclusive=True, auto_delete=True)
        with Producer(self.connection) as producer:
            producer.publish(
                {
                    'module': module,
                    'action': action
                    },
                exchange='',
                routing_key='controller_queue',
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
        return self.response


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BGPStream Historical Monitor')
    parser.add_argument('-m', '--module', type=str, dest='module', required=True,
                    help='Module name for the desired action')
    parser.add_argument('-a', '--action', type=str, dest='action', required=True,
                    help='Action to be sent (start, stop, status)')

    args = parser.parse_args()
    try:
        connection = Connection(os.getenv('RABBITMQ_HOST', 'localhost'))
        cli = ControllerCLI(connection)

        print(' [x] Requesting')
        response = cli.call(args.module, args.action)
        print(' [.] Got {}'.format(response))
    except:
        traceback.print_exc()
