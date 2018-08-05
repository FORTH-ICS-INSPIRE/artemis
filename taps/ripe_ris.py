from socketIO_client_nexus import SocketIO
from kombu import Connection, Producer, Exchange, Queue, uuid
import argparse
import traceback
import signal
import sys


def parse_ripe_ris(connection, prefix, host):
    exchange = Exchange('bgp_update', type='direct', durable=False)

    def on_ris_msg(msg):
        global msg_num
        try:
            producer = Producer(connection)
            producer.publish(
                msg,
                exchange=exchange,
                routing_key='update',
                serializer='json')
        except Exception:
            pass
            # traceback.print_exc()

    with SocketIO('http://stream-dev.ris.ripe.net/stream', wait_for_connection=False) as socket_io:
        socket_io.on('ris_message', on_ris_msg)
        socket_io.emit('ris_subscribe',
                {
                    'host': host,
                    'prefix': prefix,
                    'moreSpecific': True,
                    'lessSpecific': False,
                    'includeBody': False,
                }
        )
        socket_io.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RIPE RIS Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-r', '--host', type=str, dest='host', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()
    prefix = args.prefix
    host = args.host

    try:
        with Connection('amqp://guest:guest@localhost:5672//') as connection:
            parse_ripe_ris(connection, prefix, host)
    except KeyboardInterrupt:
        pass
