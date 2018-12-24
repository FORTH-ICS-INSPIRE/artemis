import argparse
from netaddr import IPNetwork, IPAddress
from kombu import Connection, Producer, Exchange
# install as described in https://bgpstream.caida.org/docs/install/pybgpstream
import _pybgpstream
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST, get_logger


log = get_logger()


def run_bgpstream_beta_bmp(prefixes=[]):
    '''
    Retrieve all elements related to a list of prefixes
    https://bgpstream.caida.org/docs/api/pybgpstream/_pybgpstream.html

    :param prefix: <str> input prefix

    :return: -
    '''

    # create a new bgpstream instance
    stream = _pybgpstream.BGPStream()

    # set BMP data interface
    stream.set_data_interface('beta-bmp-stream')

    # filter prefixes
    for prefix in prefixes:
        stream.add_filter('prefix', prefix)

    # filter record type
    stream.add_filter('record-type', 'updates')

    # set live mode
    stream.set_live_mode()

    # start the stream
    stream.start()

    with Connection(RABBITMQ_HOST) as connection:
        exchange = Exchange(
            'bgp-update',
            channel=connection,
            type='direct',
            durable=False)
        exchange.declare()
        producer = Producer(connection)
        while True:
            # get next record
            try:
                rec = stream.get_next_record()
            except BaseException:
                continue
            if (rec.status != 'valid') or (rec.type != 'update'):
                continue

            # get next element
            try:
                elem = rec.get_next_elem()
            except BaseException:
                continue

            while elem:
                if elem.type in ['A', 'W']:
                    this_prefix = str(elem.fields['prefix'])
                    service = 'betabmp|{}|{}'.format(
                        str(rec.project), str(rec.collector))
                    type_ = elem.type
                    if type_ == 'A':
                        as_path = elem.fields['as-path'].split(' ')
                        communities = [{'asn': int(comm.split(':')[0]), 'value': int(comm.split(':')[1])}
                                       for comm in elem.fields['communities']]
                    else:
                        as_path = []
                        communities = []
                    timestamp = float(rec.time)
                    peer_asn = elem.peer_asn

                    for prefix in prefixes:
                        base_ip, mask_length = this_prefix.split('/')
                        our_prefix = IPNetwork(prefix)
                        if IPAddress(base_ip) in our_prefix and int(
                                mask_length) >= our_prefix.prefixlen:
                            msg = {
                                'type': type_,
                                'timestamp': timestamp,
                                'path': as_path,
                                'service': service,
                                'communities': communities,
                                'prefix': this_prefix,
                                'peer_asn': peer_asn
                            }
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
                                log.warning(
                                    'Invalid format message: {}'.format(msg))
                try:
                    elem = rec.get_next_elem()
                except BaseException:
                    continue


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Beta BMP Live Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')

    try:
        run_bgpstream_beta_bmp(
            prefixes)
    except Exception:
        log.exception('exception')
    except KeyboardInterrupt:
        pass
