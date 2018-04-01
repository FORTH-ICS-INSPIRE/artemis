#!/usr/bin/env python

import os
import json
import argparse
from netaddr import IPNetwork

dir_path = os.path.dirname(os.path.realpath(__file__))
MITIGATION_SCRIPTS_DIR = "{}/../routers/quagga".format(dir_path)
PY_BIN = 'python'
QC_PY = '{}/quagga_command.py'.format(MITIGATION_SCRIPTS_DIR)
MTS_PY = '{}/moas_tcp_sender.py'.format(MITIGATION_SCRIPTS_DIR)
LOCAL_ASN = 65001
LOCAL_TELNET_IP = "192.168.101.1"
LOCAL_TELNET_PORT = 2605


def announce_prefix(
    prefix=None,
    local_asn=None,
    local_telnet_ip=None,
    local_telnet_port=None):

    os.system('{} {} -th {} -tp {} -la {} -ap {}'.format(
        PY_BIN,
        QC_PY,
        local_telnet_ip,
        local_telnet_port,
        local_asn,
        prefix))

def deaggregate_prefix(
    prefix=None,
    local_asn=None,
    local_telnet_ip=None,
    local_telnet_port=None):

    deaggr_prefixes = Deaggr(prefix, 24).get_subprefixes()
    if len(deaggr_prefixes) > 0:
        for deagg_prefix in deaggr_prefixes:
            announce_prefix(
                prefix=deagg_prefix,
                local_asn=local_asn,
                local_telnet_ip=local_telnet_ip,
                local_telnet_port=local_telnet_port)

# def moas_outsource(
#     prefix=None,
#     moas_asn=None,
#     moas_ip=None,
#     moas_port=None):
#
#     os.system('{} {} -r {} -p {} -m {}'.format(
#         PY_BIN,
#         MTS_PY,
#         moas_ip,
#         moas_port,
#         prefix))


class Deaggr:

    def __init__(self, prefix, max_deaggr):

        self.max_deaggr = max_deaggr
        self.__prefix = prefix
        self.__subprefixes = []
        self.__calc_subprefixes()

    def __calc_subprefixes(self):
        net = IPNetwork(self.__prefix)
        self.__subprefixes = list()
        # if new prefix len exceeds ipv4 or ipv6 max lengths
        if net.prefixlen < self.max_deaggr:
            new_prefixlen = net.prefixlen + 1
            self.__subprefixes = net.subnet(new_prefixlen)

    def print_subprefixes(self):
        for subprefix in self.__subprefixes:
            print(subprefix)

    def get_subprefixes(self):
        prefixes = []
        for prefix in self.__subprefixes:
            prefixes.append(str(prefix))

        return prefixes


def main():
    parser = argparse.ArgumentParser(description="mininet demo mitigation script that performs deaggregation")
    parser.add_argument('-i', '--input_hijack', dest='hijack', type=str, help='hijack info in json format', required=True)
    args = parser.parse_args()

    # format of decode hijack info
    # {
    #     'id': <int>,
    #     'type': <str>,
    #     'prefix': <str>,
    #     'hijack_as': <str>,
    #     'num_peers_seen': <int>,
    #     'num_asns_inf': <int>,
    #     'time_started': <float>,
    #     'time_last_updated': <float>
    # }
    hijack_info = json.loads(args.hijack)
    print(hijack_info)

    if IPNetwork(hijack_info['prefix']).prefixlen < 24:
        print('[CUSTOM MITIGATION] Resolving hijack {} via prefix deaggregation...'.format(hijack_info['id']))
        deaggregate_prefix(
            prefix=hijack_info['prefix'],
            local_asn=LOCAL_ASN,
            local_telnet_ip=LOCAL_TELNET_IP,
            local_telnet_port=LOCAL_TELNET_PORT)
    else:
        print('[CUSTOM MITIGATION] Cannot deaggregate prefix {} due to filtering!'.format(hijack_info['prefix']))
    #
    # print('[CUSTOM MITIGATION] Resolving hijack {} via MOAS outsourcing...'.format(hijack_info['id']))
    #
    # announce_prefix(
    #     prefix=hijack_info['prefix'],
    #     local_asn=LOCAL_ASN,
    #     local_telnet_ip=LOCAL_TELNET_IP,
    #     local_telnet_port=LOCAL_TELNET_PORT)
    #
    # moas_outsource(
    #     prefix=hijack_info['prefix'],
    #     moas_asn=MOAS_ASN,
    #     moas_ip=MOAS_IP,
    #     moas_port=MOAS_PORT)

if __name__ == '__main__':
    main()
