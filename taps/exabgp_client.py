import sys
import os
from socketIO_client import SocketIO
import argparse
from kombu import Connection, Producer, Exchange, Queue, uuid
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST

class ExaBGP():


    def __init__(self, prefixes, address, port):
        self.config = {}
        self.config['host'] = str(address) + ":" + str(port)
        self.config['prefixes'] = prefixes
        self.flag = True


    def start_loop(self):
        with Connection(RABBITMQ_HOST) as connection:
            while(self.flag):
                self.start(connection)


    def start(self, connection):
        self.connection = connection
        self.exchange = Exchange('bgp_update', type='direct', durable=False)

        socketIO = SocketIO("http://" + str(self.config['host']))
        #print("[ExaBGP] %s monitor service is up for prefixes %s" %
        #      (self.config['host'],  self.config['prefixes']))

        def on_connect(*args):
            prefixes_ = {"prefixes": self.config['prefixes']}
            socketIO.emit("exa_subscribe", prefixes_)

        def on_pong(*args):
            socketIO.emit("ping")

        def exabgp_msg(bgp_message):
            msg = {
                'type': bgp_message['type'],
                'communities': [], # TODO: mark them according to the m-format!
                'timestamp': bgp_message['timestamp'],
                'path': bgp_message['path'],
                'service': 'ExaBGP {}'.format(self.config['host']),
                'prefix': bgp_message['prefix']
            }
            if mformat_validator(msg):
                producer = Producer(connection)
                msgs = normalize_msg_path(msg)
                for msg in msgs:
                    key_generator(msg)
                    producer.publish(
                        msg,
                        exchange=self.exchange,
                        routing_key='update',
                        serializer='json'
                    )

        # not used yet (TODO)
        def on_reconnecting():
            print("ExaBGP host ", self.config['host'], " reconnecting.")

        # not used yet (TODO)
        def on_reconnect_error():
            print("ExaBGP host ", self.config['host'], " reconnect error.")

        def on_disconnect():
            print("ExaBGP host ", self.config['host'], " disconnected.")
            socketIO.close()

        # not used yet (TODO)
        def on_error():
            print("ExaBGP host ", self.config['host'], " error.")

        socketIO.on("connect", on_connect)
        socketIO.on("disconnect", on_disconnect)
        socketIO.on("pong", on_pong)
        socketIO.on("exa_message", exabgp_msg)
        #socketIO.on("reconnecting", on_reconnecting)
        #socketIO.on("reconnect_error", on_reconnect_error)
        #socketIO.on("error", on_error)

        socketIO.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ExaBGP Monitor Client')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-r', '--host', type=str, dest='host', default=None,
                        help='Prefix to be monitored')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')
    (address, port) = args.host.split(':')
    exa = ExaBGP(prefixes, address, port)
    try:
        exa.start()
    except KeyboardInterrupt:
        pass

