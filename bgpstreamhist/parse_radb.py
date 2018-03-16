#!/usr/bin/env/python3


import sys
import os
import argparse
import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import netaddr
import ujson as json
import time


RADB_QUERY_URL = 'http://www.radb.net/query/'


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


def extract_valid_asn(asn_str=None):
    """
    Get a valid ASN in the form "AS<ASN>"

    :param asn_str: <str> AS string
    :return: <str> valid ASN
    """
    asn_match = re.match('^([A,a][S,s])?(\d+)$', asn_str)
    if asn_match:
        return 'AS{}'.format(asn_match.group(2))

    return None


def dump_data(data=None, file=None):
    """
    Dump data in json format to file

    :param data: <dict|list> (json-able)
    :param file: <str> file on which to dump data
    :return: -
    """
    with open(file, 'w') as f:
        json.dump(data, f)
    print("Results written on {}".format(file))

    return


def main():
    parser = argparse.ArgumentParser(description="parse information from RADB for a specific prefix or ASN")
    parser.add_argument('-p', '--prefix', dest='prefix', type=str, help='prefix to check (do not set if asn)', default='')
    parser.add_argument('-a', '--asn', dest='asn', type=str, help='asn to check (do not set if prefix)', default='')
    parser.add_argument('-o', '--output_dir', dest='output_dir', type=str, help='folder where the output json will be stored', default='.')
    args = parser.parse_args()

    query_prefix = None
    query_asn = None
    query_value = None
    if args.prefix != '':
        if is_valid_ip_prefix(args.prefix):
            query_prefix = args.prefix
            query_value = query_prefix
    elif args.asn != '':
        query_asn = extract_valid_asn(args.asn)
        query_value = query_asn

    print('Value to query = {}'.format(query_value))
    assert query_value is not None, "not valid prefix or asn to query!"

    parsed_data = []
    if not os.path.isfile(args.output_dir):
        os.mkdir(args.output_dir)
    out_file = '{}/query_value_{}_timestamp_{}'.format(args.output_dir,
                                                       str(query_value).replace('/','+'),
                                                       int(time.time()))
    post_params = {
        'keywords': query_value
    }
    post_args = urllib.parse.urlencode(post_params).encode("utf-8")
    resp = None
    try:
        post_req = urllib.request.Request(RADB_QUERY_URL, post_args)
        resp = urllib.request.urlopen(post_req)
    except:
        print('ERROR: Could not fetch data from RADB')
        dump_data(parsed_data, out_file)
        sys.exit(0)

    page = resp.read()
    soup = BeautifulSoup(page, 'lxml')
    table_contents = soup.find_all('tt')
    if len(table_contents) == 0:
        print("WARNING: No table found!")
        dump_data(parsed_data, out_file)
        sys.exit(0)
    elif len(table_contents) > 1:
        print("WARNING: More than one tables found! Will consider only the first!")

    table_content = table_contents[0]
    for br in table_content.find_all('br'):
        br.replace_with('\n')
    table_content = str(table_content)

    new_element = True
    parsed_data_index = -1
    for line in table_content.split('\n'):
        line_match = re.match('(.*):(.*)', line)
        if line_match:
            key = line_match.group(1).strip(' ')
            value = line_match.group(2).strip(' ')
            if new_element:
                parsed_data.append([])
                parsed_data_index += 1
                new_element = False
            parsed_data[parsed_data_index].append({key: value})
        elif re.match('^\s*$', line):
            new_element = True

    dump_data(parsed_data, out_file)


if __name__ == '__main__':
    main()
