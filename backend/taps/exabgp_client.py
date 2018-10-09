from socketIO_client import SocketIO, BaseNamespace
import argparse
from kombu import Connection, Producer, Exchange
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST
import traceback
import signal


class ExaBGP():

    def __init__(self, prefixes, host):
        self.host = host
        self.prefixes = prefixes
        self.sio = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def start(self):
        with Connection(RABBITMQ_HOST) as connection:
            self.connection = connection
            self.exchange = Exchange(
                'bgp-update',
                channel=connection,
                type='direct',
                durable=False)
            self.exchange.declare()

            try:
                self.sio = SocketIO('http://' + self.host, namespace=BaseNamespace)

                def exabgp_msg(bgp_message):
                    msg = {
                        'type': bgp_message['type'],
                        'communities': bgp_message.get('communities', []),
                        'timestamp': bgp_message['timestamp'],
                        'path': bgp_message.get('path', []),
                        'service': 'exabgp|{}'.format(self.host),
                        'prefix': bgp_message['prefix'],
                        'peer_asn': int(bgp_message['peer_asn'])
                    }
                    if mformat_validator(msg):
                        with Producer(connection) as producer:
                            msgs = normalize_msg_path(msg)
                            for msg in msgs:
                                key_generator(msg)
                                producer.publish(
                                    msg,
                                    exchange=self.exchange,
                                    routing_key='update',
                                    serializer='json'
                                )

                self.sio.on('exa_message', exabgp_msg)
                self.sio.emit('exa_subscribe', {'prefixes': self.prefixes})
                self.sio.wait()
            except KeyboardInterrupt:
                self.exit()

    def exit(self):
        print('Exiting ExaBGP')
        if self.sio is not None:
            self.sio.disconnect()
            self.sio.wat()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ExaBGP Monitor Client')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-r', '--host', type=str, dest='host', default=None,
                        help='Prefix to be monitored')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')
    exa = ExaBGP(prefixes, args.host)
    print('Starting ExaBGP on {} for {}'.format(args.host, prefixes))
    try:
        exa.start()
    except BaseException:
        traceback.print_exc()
