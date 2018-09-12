#!/usr/bin/env python


import argparse
import os
import csv
import time
import ujson as json
from pprint import pprint as pp


def format_timestamp(timestamp):
    """
    Format UNIX epoch timestamp to a human-understandable time format

    :param timestamp: <int> UNIX epochs
    :return: <str> YYYY-MM-DD HH:MM:SS
    """
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def main():
    parser = argparse.ArgumentParser(description="analyze the BGP records of BGPStream")
    parser.add_argument('-i', '--input_file', dest='input_file', type=str, help='.csv file to check', required=True)
    parser.add_argument('-o', '--out_dir', dest='output_dir', type=str, help='output directory', required=True)
    args = parser.parse_args()

    filename_elems = args.input_file.split('-')
    start_time = format_timestamp(int(filename_elems[1].split('_')[1]))
    end_time = format_timestamp(int(filename_elems[2].split('_')[1].split('.csv')[0]))

    observed_prefixes = {}
    with open(args.input_file, 'r') as f:
        csv_reader = csv.reader(f, delimiter='|')
        for row in csv_reader:
            if len(row) == 8:
                timestamp = int(row[6])
                prefix = row[0]
                if prefix not in observed_prefixes:
                    observed_prefixes[prefix] = {
                        'origins': {},
                        'first_hops': {}
                    }
                origin_asn = row[1]
                if origin_asn != '':
                    if origin_asn not in observed_prefixes[prefix]['origins']:
                        observed_prefixes[prefix]['origins'][origin_asn] = set()
                    observed_prefixes[prefix]['origins'][origin_asn].add(timestamp)
    
                if len(row[2]) > 1:
                    first_hop = row[2].split(',')[-2]
                    first_hop = "{}-{}".format(first_hop, origin_asn)
                    if first_hop not in observed_prefixes[prefix]['first_hops']:
                        observed_prefixes[prefix]['first_hops'][first_hop] = set()
                    observed_prefixes[prefix]['first_hops'][first_hop].add(timestamp)

    for prefix in observed_prefixes:
        for origin_asn in observed_prefixes[prefix]['origins']:
            observed_prefixes[prefix]['origins'][origin_asn] = sorted(list(observed_prefixes[prefix]['origins'][origin_asn]))
            for i,timestamp in enumerate(observed_prefixes[prefix]['origins'][origin_asn]):
                observed_prefixes[prefix]['origins'][origin_asn][i] = format_timestamp(timestamp)

        for first_hop in observed_prefixes[prefix]['first_hops']:
            observed_prefixes[prefix]['first_hops'][first_hop] = sorted(list(observed_prefixes[prefix]['first_hops'][first_hop]))
            for i,timestamp in enumerate(observed_prefixes[prefix]['first_hops'][first_hop]):
                observed_prefixes[prefix]['first_hops'][first_hop][i] = format_timestamp(timestamp)

    if not os.path.isdir(args.output_dir):
        os.mkdir(args.output_dir)
    out_file = '{}/{}_analyzed.json'.format(args.output_dir, args.input_file.split('/')[-1].split('.csv')[0])

    with open(out_file, 'w') as f:
        json.dump(observed_prefixes, f)

    print('REPORT FROM {} TO {} generated on {}'.format(start_time, end_time, out_file))


if __name__=='__main__':
    main()
