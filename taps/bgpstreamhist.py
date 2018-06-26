import sys
import os
import grpc
import glob
import csv
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
                if len(row) != 8:
                    continue
                # example row: 139.91.250.0/24|8522|11666,3257,174,56910,8522|routeviews|route-views.eqix|A|1517443593|11666
                this_prefix = row[0]
                if row[5] == 'A':
                    as_path = list(map(as_mapper, row[2].split(',')))
                else:
                    as_path = None
                service = "historical|{}|{}".format(row[3], row[4])
                type = row[5]
                timestamp = float(row[6])
                for prefix in prefixes:
                    base_ip, mask_length = this_prefix.split('/')
                    our_prefix = IPNetwork(prefix)
                    if IPAddress(base_ip) in our_prefix and mask_length >= our_prefix.prefixlen:
                        stub.queryMformat(mservice_pb2.MformatMessage(
                            type=type,
                            timestamp=timestamp,
                            as_path=as_path,
                            service=service,
                            prefix=this_prefix
                        ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BGPStream Historical Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-d', '--dir', type=str, dest='dir', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')
    parse_bgpstreamhist_csvs(prefixes, args.dir)

