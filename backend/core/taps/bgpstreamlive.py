import argparse
import time
from netaddr import IPNetwork, IPAddress
from kombu import Connection, Producer, Exchange
# install as described in https://bgpstream.caida.org/docs/install/pybgpstream
import _pybgpstream
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST, get_logger


START_TIME_OFFSET = 3600  # seconds
log = get_logger()


def run_bgpstream(prefixes=[], projects=[], start=0, end=0):
    """
    Retrieve all records related to a list of prefixes
    https://bgpstream.caida.org/docs/api/pybgpstream/_pybgpstream.html

    :param prefix: <str> input prefix
    :param start: <int> start timestamp in UNIX epochs
    :param end: <int> end timestamp in UNIX epochs (if 0 --> "live mode")

    :return: -
    """

    # create a new bgpstream instance and a reusable bgprecord instance
    stream = _pybgpstream.BGPStream()

    # consider collectors from given projects
    for project in projects:
        stream.add_filter('project', project)

    # filter prefixes
    for prefix in prefixes:
        stream.add_filter('prefix', prefix)

    # filter record type
    stream.add_filter('record-type', 'updates')

    # filter based on timing (if end=0 --> live mode)
    stream.add_interval_filter(start, end)

    # set live mode
    stream.set_live_mode()

    # start the stream
    stream.start()

    # print('BGPStream started...')
    # print('Projects ' + str(projects))
    # print('Prefixes ' + str(prefixes))
    # print('Start ' + str(start))
    # print('End ' + str(end))

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
            if (rec.status != "valid") or (rec.type != "update"):
                continue

            # get next element
            try:
                elem = rec.get_next_elem()
            except BaseException:
                continue

            while elem:
                if elem.type in ["A", "W"]:
                    this_prefix = str(elem.fields['prefix'])
                    service = "bgpstream|{}|{}".format(
                        str(rec.project), str(rec.collector))
                    type_ = elem.type
                    if type_ == "A":
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
    parser = argparse.ArgumentParser(description='BGPStream Live Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-m', '--mon_projects', type=str, dest='mon_projects', default=None,
                        help='projects to consider for monitoring')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')
    projects = args.mon_projects.split(',')

    try:
        run_bgpstream(
            prefixes,
            projects,
            start=int(
                time.time()) -
            START_TIME_OFFSET,
            end=0)
    except Exception:
        log.exception('exception')
    except KeyboardInterrupt:
        pass
