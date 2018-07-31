import sys
import os
import grpc
import glob
import csv
import json
import argparse
from netaddr import IPNetwork, IPAddress

# to import protogrpc, since the root package has '-'
# in the name ("artemis-tool")
this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
from protogrpc import mservice_pb2, mservice_pb2_grpc


def as_mapper(asn_str):
    if asn_str != '':
        return int(asn_str)
    return 0


def parse_bgpstreamhist_csvs(prefixes=[], input_dir=None):
    channel = grpc.insecure_channel('localhost:50051')
    stub = mservice_pb2_grpc.MessageListenerStub(channel)

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
                    communities = [mservice_pb2.Community(asn=c['asn'], value=c['value']) for c in communities]
                else:
                    as_path = None
                    communities = []
                service = "historical|{}|{}".format(row[4], row[5])
                type = row[6]
                timestamp = float(row[8])
                for prefix in prefixes:
                    base_ip, mask_length = this_prefix.split('/')
                    our_prefix = IPNetwork(prefix)
                    if IPAddress(base_ip) in our_prefix and int(mask_length) >= our_prefix.prefixlen:
                        stub.queryMformat(mservice_pb2.MformatMessage(
                            type=type,
                            timestamp=timestamp,
                            as_path=as_path,
                            service=service,
                            communities=communities,
                            prefix=this_prefix
                        ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BGPStream Historical Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-d', '--dir', type=str, dest='dir', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()
    dir = args.dir.rstrip('/')

    prefixes = args.prefix.split(',')
    parse_bgpstreamhist_csvs(prefixes, dir)

