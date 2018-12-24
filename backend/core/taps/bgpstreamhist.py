import glob
import csv
import json
import argparse
from kombu import Connection, Producer, Exchange
from netaddr import IPNetwork, IPAddress
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_HOST, get_logger


log = get_logger()


def parse_bgpstreamhist_csvs(prefixes=[], input_dir=None):

    with Connection(RABBITMQ_HOST) as connection:
        exchange = Exchange(
            'bgp-update',
            channel=connection,
            type='direct',
            durable=False)
        exchange.declare()
        producer = Producer(connection)

        for csv_file in glob.glob("{}/*.csv".format(input_dir)):
            try:
                with open(csv_file, 'r') as f:
                    csv_reader = csv.reader(f, delimiter="|")
                    for row in csv_reader:
                        try:
                            if len(row) != 9:
                                continue
                            if row[0].startswith('#'):
                                continue
                            # example row: 139.91.0.0/16|8522|1403|1403 6461 2603 21320
                            # 5408
                            # 8522|routeviews|route-views2|A|"[{""asn"":1403,""value"":6461}]"|1517446677
                            this_prefix = row[0]
                            if row[6] == 'A':
                                as_path = row[3].split(' ')
                                communities = json.loads(row[7])
                            else:
                                as_path = []
                                communities = []
                            service = "historical|{}|{}".format(row[4], row[5])
                            type_ = row[6]
                            timestamp = float(row[8])
                            peer_asn = int(row[2])
                            for prefix in prefixes:
                                try:
                                    base_ip, mask_length = this_prefix.split(
                                        '/')
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
                                except Exception:
                                    log.exception('prefix')
                        except Exception:
                            log.exception('row')
            except Exception:
                log.exception('exception')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='BGPStream Historical Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-d', '--dir', type=str, dest='dir', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()
    dir = args.dir.rstrip('/')

    prefixes = args.prefix.split(',')

    try:
        parse_bgpstreamhist_csvs(prefixes, dir)
    except Exception:
        log.exception('exception')
    except KeyboardInterrupt:
        pass
