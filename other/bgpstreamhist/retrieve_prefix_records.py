#!/usr/bin/env python


import argparse
import netaddr
import os
import sys
import csv
# install as described in https://bgpstream.caida.org/docs/install/pybgpstream
from _pybgpstream import BGPStream, BGPRecord, BGPElem


def is_valid_ip_prefix(pref_str=None):
    """
    Check if given prefix (in string format) is a valid IPv4/IPv6 prefix
    http://netaddr.readthedocs.io/en/latest/tutorial_01.html

    :param pref_str: <str> prefix
    :return: <bool> whether prefix is valid
    """
    try:
        pref = netaddr.IPNetwork(pref_str)
    except:
        return False

    return True


def run_bgpstream(prefix, start, end, out_file):
    """
    Retrieve all records related to a certain prefix for a certain time period
    and save them on a .csv file
    https://bgpstream.caida.org/docs/api/pybgpstream/_pybgpstream.html

    :param prefix: <str> input prefix
    :param start: <int> start timestamp in UNIX epochs
    :param end: <int> end timestamp in UNIX epochs
    :param out_file: <str> .csv file to store information
    format: PREFIX|ORIGIN_AS|AS_PATH|PROJECT|COLLECTOR|TYPE|TIME|PEER_ASN

    :return: -
    """
    # create a new bgpstream instance and a reusable bgprecord instance
    stream = BGPStream()
    rec = BGPRecord()

    # consider collectors from routeviews and ris
    stream.add_filter('project','routeviews')
    stream.add_filter('project','ris')

    # filter prefix
    stream.add_filter('prefix', prefix)

    # filter record type
    stream.add_filter('record-type', 'updates')

    # filter based on timing
    stream.add_interval_filter(start, end)

    # start the stream
    stream.start()

    # set the csv writer
    with open(out_file, 'w') as f:
        csv_writer = csv.writer(f, delimiter="|")

        # get next record
        while stream.get_next_record(rec):
            if (rec.status != "valid") or (rec.type != "update"):
                continue

            # get next element
            elem = rec.get_next_elem()

            while elem:
                if elem.type in ["A", "W"]:
                    elem_csv_list = []
                    if elem.type == "A":
                        elem_csv_list = [
                            str(elem.fields['prefix']),
                            str(elem.fields['as-path'].split(" ")[-1]),
                            ",".join(elem.fields['as-path'].split(" ")),
                            str(rec.project),
                            str(rec.collector),
                            str(elem.type),
                            str(elem.time),
                            str(elem.peer_asn)
                        ]
                    else:
                        elem_csv_list = [
                            str(elem.fields['prefix']),
                            "",
                            "",
                            str(rec.project),
                            str(rec.collector),
                            str(elem.type),
                            str(elem.time),
                            str(elem.peer_asn)
                        ]
                    csv_writer.writerow(elem_csv_list)

                elem = rec.get_next_elem()

    #release resources
    del rec
    del stream


def main():
    parser = argparse.ArgumentParser(description="retrieve all records related to a specific IP prefix")
    parser.add_argument('-p', '--prefix', dest='prefix', type=str, help='prefix to check', required=True)
    parser.add_argument('-s', '--start', dest='start_time', type=int, help='start timestamp (in UNIX epochs)', required=True)
    parser.add_argument('-e', '--end', dest='end_time', type=int, help='end timestamp (in UNIX epochs)', required=True)
    parser.add_argument('-o', '--out_dir', dest='output_dir', type=str, help='output dir to store the retrieved information', required=True)
    args = parser.parse_args()

    if not is_valid_ip_prefix(args.prefix):
        print("Prefix '{}' is not valid!".format(args.prefix))
        sys.exit(1)

    # for UNIX epoch timestamps, please check https://www.epochconverter.com/
    if not args.start_time < args.end_time:
        print("Start time '{}' is greater or equal than end time '{}'".format(args.start_time, args.end_time))
        sys.exit(1)

    if not os.path.isdir(args.output_dir):
        os.mkdir(args.output_dir)
    out_file = '{}/P_{}-S_{}-E_{}.csv'.format(args.output_dir,
                                              args.prefix.replace('/', '+'),
                                              args.start_time,
                                              args.end_time)
    run_bgpstream(args.prefix, args.start_time, args.end_time, out_file)


if __name__ == '__main__':
    main()
