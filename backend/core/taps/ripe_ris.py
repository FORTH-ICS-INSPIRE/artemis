from socketIO_client_nexus import SocketIO
from kombu import Connection, Producer, Exchange
import argparse
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST, get_logger


log = get_logger()
update_to_type = {
    'announcements': 'A',
    'withdrawls': 'W'
}


def normalize_ripe_ris(msg):
    if isinstance(msg, dict):
        msg['key'] = None  # initial placeholder before passing the validator
        if 'community' in msg:
            msg['communities'] = [{'asn': comm[0], 'value': comm[1]}
                                  for comm in msg['community']]
            del msg['community']
        if 'host' in msg:
            msg['service'] = 'ripe-ris|' + msg['host']
            del msg['host']
        if 'peer_asn' in msg:
            msg['peer_asn'] = int(msg['peer_asn'])
        if 'path' not in msg:
            msg['path'] = []
        if 'timestamp' in msg:
            msg['timestamp'] = float(msg['timestamp'])
        if 'type' in msg:
            del msg['type']
        if 'source' in msg:
            source = msg['source']
            if source in update_to_type:
                msg['type'] = update_to_type[source]


def parse_ripe_ris(connection, prefix, host):
    exchange = Exchange(
        'bgp-update',
        channel=connection,
        type='direct',
        durable=False)
    exchange.declare()

    def on_ris_msg(msg):
        try:
            producer = Producer(connection)
            normalize_ripe_ris(msg)
            if mformat_validator(msg):
                msgs = normalize_msg_path(msg)
                for msg in msgs:
                    key_generator(msg)
                    log.debug(msg)
                    producer.publish(
                        msg,
                        exchange=exchange,
                        routing_key='update',
                        serializer='json'
                    )
            else:
                log.warning('Invalid format message: {}'.format(msg))
        except Exception:
            log.exception('exception')

    with SocketIO('http://stream-dev.ris.ripe.net/stream2', wait_for_connection=False) as socket_io:
        socket_io.on('ris_message', on_ris_msg)
        socket_io.emit('ris_subscribe',
                       {
                           'host': host,
                           'type': 'UPDATE',
                           'prefix': prefix,
                           'moreSpecific': True,
                           'lessSpecific': False,
                           'socketOptions': {
                               'includeBody': False,
                               'explodePrefixes': True,
                           }
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
        with Connection(RABBITMQ_HOST) as connection:
            parse_ripe_ris(connection, prefix, host)
    except Exception:
        log.exception('exception')
    except KeyboardInterrupt:
        pass
