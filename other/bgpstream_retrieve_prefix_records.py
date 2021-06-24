#!/usr/bin/env python
import argparse
import csv
import os
import sys

import netaddr
import ujson
import pybgpstream

# install as described in https://bgpstream.caida.org/docs/install/pybgpstream


def is_valid_ip_prefix(pref_str=None):
    """
    Check if given prefix (in string format) is a valid IPv4/IPv6 prefix
    http://netaddr.readthedocs.io/en/latest/tutorial_01.html

    :param pref_str: <str> prefix
    :return: <bool> whether prefix is valid
    """
    try:
        netaddr.IPNetwork(pref_str)
    except Exception:
        return False
    return True

def func_communities_to_json(value):
    liste=[]
    for i in value:
        a_1=i.split(':')
        a_2={'asn':int(a_1[0]), 'value':int(a_1[1])}
        liste.append(a_2)
    json_file=ujson.dumps(liste)
    return json_file

def run_bgpstream(prefix, start, end, out_file):
    """
    Retrieve all records related to a certain prefix for a certain time period
    and save them on a .csv file
    https://bgpstream.caida.org/docs/api/pybgpstream/_pybgpstream.html

    :param prefix: <str> input prefix
    :param start: <int> start timestamp in UNIX epochs
    :param end: <int> end timestamp in UNIX epochs
    :param out_file: <str> .csv file to store information
    format: PREFIX|ORIGIN_AS|PEER_AS|AS_PATH|PROJECT|COLLECTOR|TYPE|COMMUNITIES|TIME
    :return: -
    """
    # create a new bgpstream instance and a reusable bgprecord instance
    # More to information about filter: https://github.com/CAIDA/bgpstream/blob/master/FILTERING
    stream = pybgpstream.BGPStream(
        from_time=start, until_time=end, # filter based on timing
        collectors=[], # empty=use all RRC from RIPE and RouteViews
        record_type="updates", # filter record type
        filter="prefix any "+str(prefix),  # filter prefix
    )

    # set the csv writer
    with open(out_file, "w") as f:
        csv_writer = csv.writer(f, delimiter="|")

        for elem in stream:
            if (elem.status != "valid") or (elem.record.rec.type != "update"):
                continue
            if elem.type in ["A", "W"]:
                elem_csv_list = []
                if elem.type == "A":
                    elem_csv_list = [
                        str(elem.fields["prefix"]),
                        str(elem.fields["as-path"].split(" ")[-1]),
                        str(elem.peer_asn),
                        str(elem.fields["as-path"]),
                        str(elem.project),
                        str(elem.collector),
                        str(elem.type),
                        func_communities_to_json(elem.fields["communities"]),
                        str(elem.time),
                    ]
                else:
                    elem_csv_list = [
                        str(elem.fields["prefix"]),
                        "",
                        str(elem.peer_asn),
                        "",
                        str(elem.project),
                        str(elem.collector),
                        str(elem.type),
                        ujson.dumps([]),
                        str(elem.time),
                    ]
                csv_writer.writerow(elem_csv_list)


def main():
    parser = argparse.ArgumentParser(
        description="retrieve all records related to a specific IP prefix"
    )
    parser.add_argument(
        "-p", "--prefix", dest="prefix", type=str, help="prefix to check", required=True
    )
    parser.add_argument(
        "-s",
        "--start",
        dest="start_time",
        type=int,
        help="start timestamp (in UNIX epochs)",
        required=True,
    )
    parser.add_argument(
        "-e",
        "--end",
        dest="end_time",
        type=int,
        help="end timestamp (in UNIX epochs)",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--out_dir",
        dest="output_dir",
        type=str,
        help="output dir to store the retrieved information",
        required=True,
    )
    args = parser.parse_args()

    if not is_valid_ip_prefix(args.prefix):
        print("Prefix '{}' is not valid!".format(args.prefix))
        sys.exit(1)

    # for UNIX epoch timestamps, please check https://www.epochconverter.com/
    if not args.start_time < args.end_time:
        print(
            "Start time '{}' is greater or equal than end time '{}'".format(
                args.start_time, args.end_time
            )
        )
        sys.exit(1)

    output_dir = args.output_dir.rstrip("/")
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    out_file = "{}/PREFIX_{}-START_{}-END_{}.csv".format(
        args.output_dir, args.prefix.replace("/", "+"), args.start_time, args.end_time
    )
    run_bgpstream(args.prefix, args.start_time, args.end_time, out_file)


if __name__ == "__main__":
    main()
