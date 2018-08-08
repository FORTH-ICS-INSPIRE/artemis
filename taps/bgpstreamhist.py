import sys
import os
import glob
import csv
import hashlib
import json
import argparse
from kombu import Connection, Producer, Exchange, Queue, uuid
from netaddr import IPNetwork, IPAddress
from utils import mformat_validator, key_generator, RABBITMQ_HOST


def as_mapper(asn_str):
    if asn_str != '':
        return int(asn_str)
    return 0


def parse_bgpstreamhist_csvs(prefixes=[], input_dir=None):

    with Connection(RABBITMQ_HOST) as connection:
        exchange = Exchange('bgp_update', type='direct', durable=False)
        producer = Producer(connection)

        for csv_file in glob.glob("{}/*.csv".format(input_dir)):
            with open(csv_file, 'r') as f:
                csv_reader = csv.reader(f, delimiter="|")
                for row in csv_reader:
                    if len(row) != 9:
                        continue
                    # example row: 139.91.0.0/16|8522|1403|1403,6461,2603,21320,5408,8522|routeviews|route-views2|A|"[{""asn"":1403,""value"":6461}]"|1517446677
                    this_prefix = row[0]
                    if row[6] == 'A':
                        as_path = list(map(as_mapper, row[3].split(',')))
                        communities = json.loads(row[7])
                    else:
                        as_path = None
                        communities = []
                    service = "historical|{}|{}".format(row[4], row[5])
                    type_ = row[6]
                    timestamp = float(row[8])
                    for prefix in prefixes:
                        base_ip, mask_length = this_prefix.split('/')
                        our_prefix = IPNetwork(prefix)
                        if IPAddress(base_ip) in our_prefix and int(mask_length) >= our_prefix.prefixlen:
                            msg = {
                                'type': type_,
                                'timestamp': timestamp,
                                'path': as_path,
                                'service': service,
                                'communities': communities,
                                'prefix': this_prefix
                            }
                            if mformat_validator(msg):
                                key_generator(msg)
                                producer.publish(
                                    msg,
                                    exchange=exchange,
                                    routing_key='update',
                                    serializer='json'
                                )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BGPStream Historical Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-d', '--dir', type=str, dest='dir', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()
    dir = args.dir.rstrip('/')

    prefixes = args.prefix.split(',')

    try:
        parse_bgpstreamhist_csvs(prefixes, dir)
    except KeyboardInterrupt:
        pass

