#!/usr/bin/env python3

import glob
import csv
import argparse
import yaml
from collections import OrderedDict as odict
from pprint import pprint as pp

class CustomAnchorPrefASNs(yaml.Dumper):
    def __init__(self,*args,**kwargs):
        super(CustomAnchorPrefASNs,self).__init__(*args,**kwargs)
        self.depth = 0
        self.basekey = None
        self.should_anchor_next = False

    def anchor_node(self, node):
        self.depth += 1
        if self.depth == 4:
            self.basekey = str(node.value)
        elif self.depth == 5:
            self.anchors[node] = str(self.basekey)
            self.depth -= 2
        super(CustomAnchorPrefASNs,self).anchor_node(node)

def __remove_prepending(seq):
    last_add = None
    new_seq = []
    for x in seq:
        if last_add != x:
            last_add = x
            new_seq.append(int(x))

    is_loopy = False
    if len(set(seq)) != len(new_seq):
        is_loopy = True
    return (new_seq, is_loopy)

def __clean_loops(seq):
    # use inverse direction to clean loops in the path of the traffic
    seq_inv = seq[::-1]
    new_seq_inv = []
    for x in seq_inv:
        if x not in new_seq_inv:
            new_seq_inv.append(x)
        else:
            x_index = new_seq_inv.index(x)
            new_seq_inv = new_seq_inv[:x_index+1]
    return new_seq_inv[::-1]

def __clean_as_path(as_path):
    (clean_as_path, is_loopy) = __remove_prepending(as_path)
    if is_loopy:
        clean_as_path = __clean_loops(clean_as_path)
    return clean_as_path

def as_mapper(asn_str):
    if asn_str != '':
        return int(asn_str)
    return 0

def parse_bgpstreamhist_csvs(input_dir=None):

    prefixes = set()
    prefix_pols = {}
    all_asns = set()
    for csv_file in glob.glob("{}/*.csv".format(input_dir)):
        with open(csv_file, 'r') as f:
            csv_reader = csv.reader(f, delimiter="|")
            for row in csv_reader:
                if len(row) != 9:
                    continue
                # example row: 139.91.0.0/16|8522|6830|6830,2603,21320,5408,8522|routeviews|route-views.eqix|A|"[{""asn"":2603,""value"":340},{""asn"":2603,""value"":20965},{""asn"":2603,""value"":64110},{""asn"":2603,""value"":64113},{""asn"":5408,""value"":120},{""asn"":5408,""value"":1003},{""asn"":6830,""value"":16000},{""asn"":6830,""value"":16011},{""asn"":6830,""value"":33104},{""asn"":20965,""value"":155},{""asn"":20965,""value"":64914},{""asn"":20965,""value"":65532},{""asn"":20965,""value"":65533},{""asn"":20965,""value"":65534}]"|1517501179
                prefix = row[0]
                if prefix == '0.0.0.0/0':
                    continue
                if prefix not in prefix_pols:
                    prefix_pols[prefix] = {
                        'origins': set(),
                        'neighbors': set()
                    }
                prefixes.add(prefix)
                if row[1] == '':
                    continue
                typ = row[6]
                if typ == 'A':
                    as_path = list(map(as_mapper, row[3].split(',')))
                    as_path = __clean_as_path(as_path)
                    if len(as_path) > 0:
                        all_asns.add(as_path[-1])
                        prefix_pols[prefix]['origins'].add(as_path[-1])
                    if len(as_path) > 1:
                        all_asns.add(as_path[-2])
                        prefix_pols[prefix]['neighbors'].add(as_path[-2])
                else:
                    as_path = None

    return (prefixes, all_asns, prefix_pols)

def create_prefix_defs(prefixes):
    yaml_conf = {
        'prefixes' : {}
    }
    for prefix in prefixes:
        prefix_str = 'prefix_{}'.format(prefix.replace('.', '_').replace('/', '_'))
        yaml_conf['prefixes'][prefix_str] = prefix
    return yaml_conf

def create_monitor_defs():
    riperis = []
    for i in range(1,24):
        if i < 10:
            riperis.append('rrc0{}'.format(i))
        else:
            riperis.append('rrc{}'.format(i))
    yaml_conf= {
        'monitors' : {
            'riperis': riperis,
            'bgpstreamlive': ['routeviews', 'ris']
            # 'exabgp': ['ip': '192.168.1.1', 'port': 5000, ...],
            # 'bgpstreamhist': '/home/vkotronis/Desktop/git_projects/artemis-tool/other/bgpstreamhist/test_dir2'
        }
    }
    return yaml_conf

def create_asn_defs(asns):
    yaml_conf = {
        'asns': {}
    }
    for asn in asns:
        asn_str = 'AS{}'.format(asn)
        yaml_conf['asns'][asn_str] = asn
    return yaml_conf

def create_rule_defs(prefix_pols):
    yaml_conf= {
        'rules': []
    }
    for prefix in prefix_pols:
        prefix_str = 'prefix_{}'.format(prefix.replace('.', '_').replace('/', '_'))
        pol_dict = {
            'prefixes': prefix_str,
            'origin_asns': ['AS{}'.format(asn) for asn in prefix_pols[prefix]['origins']],
            'neighbors': ['AS{}'.format(asn) for asn in prefix_pols[prefix]['neighbors']],
            'mitigation': 'manual'
        }
        yaml_conf['rules'].append(pol_dict)
    return yaml_conf

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BGPStream Historical Monitor')
    parser.add_argument('-d', '--dir', type=str, dest='dir', default=None,
                        help='Directory with csvs to read')
    parser.add_argument('-y', '--yaml_file', dest='yaml_file', required=None,
                        help='yaml output file')
    args = parser.parse_args()
    csv_dir = args.dir.strip('/')

    (prefixes, asns, prefix_pols) = parse_bgpstreamhist_csvs(csv_dir)

    with open(args.yaml_file, 'w') as f:
        f.write('#\n')
        f.write('# ARTEMIS Configuration File\n')
        f.write('#\n')
        f.write('\n')

        f.write('# Start of Prefix Definitions\n')
        prefixes_yaml_conf = create_prefix_defs(prefixes)
        yaml.dump(prefixes_yaml_conf, f, default_flow_style=False, Dumper=CustomAnchorPrefASNs)
        f.write('# End of Prefix Definitions\n')
        f.write('\n')

        f.write('# Start of Monitor Definitions\n')
        monitor_yaml_conf = create_monitor_defs()
        yaml.dump(monitor_yaml_conf, f, default_flow_style=False)
        f.write('# End of Monitor Definitions\n')
        f.write('\n')

        f.write('# Start of ASN Definitions\n')
        asns_yaml_conf = create_asn_defs(asns)
        yaml.dump(asns_yaml_conf, f, default_flow_style=False, Dumper=CustomAnchorPrefASNs)
        f.write('# End of ASN Definitions\n')
        f.write('\n')

        f.write('# Start of Rule Definitions\n')
        rules_yaml_conf = create_rule_defs(prefix_pols)
        yaml.dump(rules_yaml_conf, f, default_flow_style=False)
        f.write('# End of Rule Definitions\n')
