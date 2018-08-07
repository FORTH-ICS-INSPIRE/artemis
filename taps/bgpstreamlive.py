import sys
import os
import argparse
import hashlib
import time
from netaddr import IPNetwork, IPAddress
from kombu import Connection, Producer, Exchange, Queue, uuid
# install as described in https://bgpstream.caida.org/docs/install/pybgpstream
from _pybgpstream import BGPStream, BGPRecord, BGPElem


START_TIME_OFFSET = 3600 # seconds


def as_mapper(asn_str):
    if asn_str != '':
        return int(asn_str)
    return 0

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
    stream = BGPStream()
    rec = BGPRecord()

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

    with Connection('amqp://guest:guest@localhost:5672//') as connection:
        exchange = Exchange('bgp_update', type='direct', durable=False)
        producer = Producer(connection)
        while True:
            # get next record
            try:
                stream.get_next_record(rec)
            except:
                continue
            if (rec.status != "valid") or (rec.type != "update"):
                continue

            # get next element
            try:
                elem = rec.get_next_elem()
            except:
                continue

            while elem:
                if elem.type in ["A", "W"]:
                    this_prefix = str(elem.fields['prefix'])
                    service = "bgpstream|{}|{}".format(str(rec.project), str(rec.collector))
                    type_ = elem.type
                    if elem.type == "A":
                        as_path = list(map(as_mapper, elem.fields['as-path'].split(" ")))
                        communities = elem.fields['communities']
                    else:
                        as_path = ''
                        communities = []
                    timestamp = float(elem.time)

                    for prefix in prefixes:
                        base_ip, mask_length = this_prefix.split('/')
                        our_prefix = IPNetwork(prefix)
                        if IPAddress(base_ip) in our_prefix and int(mask_length) >= our_prefix.prefixlen:
                            producer.publish(
                                    {
                                        'type': type_,
                                        'timestamp': timestamp,
                                        'path': as_path,
                                        'service': service,
                                        'communities': communities,
                                        'prefix': this_prefix,
                                        'key': hash(frozenset([
                                            str(this_prefix),
                                            str(as_path),
                                            str(type_),
                                            str(service),
                                            str(timestamp)
                                        ]))
                                    },
                                    exchange=exchange,
                                    routing_key='update',
                                    serializer='json'
                            )

                try:
                    elem = rec.get_next_elem()
                except:
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
        run_bgpstream(prefixes, projects, start=int(time.time()) - START_TIME_OFFSET, end=0)
    except KeyboardInterrupt:
        pass

