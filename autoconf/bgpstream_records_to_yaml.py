#!/usr/bin/env python3

import glob
import csv
import argparse
import ruamel.yaml


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


def __as_mapper(asn_str):
    if asn_str != '':
        try:
            return int(asn_str)
        except:
            return 0
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
                    as_path = list(map(__as_mapper, row[3].split(',')))
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


def create_prefix_defs(yaml_conf, prefixes):
    yaml_conf['prefixes'] = ruamel.yaml.comments.CommentedMap()
    for prefix in prefixes:
        prefix_str = 'prefix_{}'.format(prefix.replace('.', '_').replace('/', '_'))
        yaml_conf['prefixes'][prefix_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['prefixes'][prefix_str].append(prefix)
        yaml_conf['prefixes'][prefix_str].yaml_set_anchor(prefix_str)


def create_monitor_defs(yaml_conf):
    yaml_conf['monitors'] = ruamel.yaml.comments.CommentedMap()
    riperis = []
    for i in range(1,24):
        if i < 10:
            riperis.append('rrc0{}'.format(i))
        else:
            riperis.append('rrc{}'.format(i))
    yaml_conf['monitors']['riperis'] = riperis
    yaml_conf['monitors']['bgpstreamlive'] = ['routeviews', 'ris']
    # 'exabgp': ['ip': '192.168.1.1', 'port': 5000, ...],
    # 'bgpstreamhist': '/home/vkotronis/Desktop/git_projects/artemis-tool/other/bgpstreamhist/test_dir2'


def create_asn_defs(yaml_conf, asns):
    yaml_conf['asns'] = ruamel.yaml.comments.CommentedMap()
    for asn in asns:
        asn_str = 'AS{}'.format(asn)
        yaml_conf['asns'][asn_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['asns'][asn_str].append(asn)
        yaml_conf['asns'][asn_str].yaml_set_anchor(asn_str)


def create_rule_defs(yaml_conf, prefix_pols):
    yaml_conf['rules'] = ruamel.yaml.comments.CommentedSeq()
    for prefix in prefix_pols:
        pol_dict = ruamel.yaml.comments.CommentedMap()
        prefix_str = 'prefix_{}'.format(prefix.replace('.', '_').replace('/', '_'))
        pol_dict['prefixes'] = [yaml_conf['prefixes'][prefix_str]]
        pol_dict['origin_asns'] = [yaml_conf['asns']['AS{}'.format(asn)] for asn in prefix_pols[prefix]['origins']],
        pol_dict['neighbors'] = [yaml_conf['asns']['AS{}'.format(asn)] for asn in prefix_pols[prefix]['neighbors']],
        pol_dict['mitigation'] = 'manual'
        yaml_conf['rules'].append(pol_dict)


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
        # initial comments
        f.write('#\n')
        f.write('# ARTEMIS Configuration File\n')
        f.write('#\n')
        f.write('\n')

        # initialize conf
        yaml = ruamel.yaml.YAML()
        yaml_conf = ruamel.yaml.comments.CommentedMap()

        # populate conf
        create_prefix_defs(yaml_conf, prefixes)
        create_monitor_defs(yaml_conf)
        create_asn_defs(yaml_conf, asns)
        create_rule_defs(yaml_conf, prefix_pols)

        # in-file comments
        yaml_conf.yaml_set_comment_before_after_key('prefixes',
                                                    before='Start of Prefix Definitions')
        yaml_conf.yaml_set_comment_before_after_key('monitors',
                                                    before='End of Prefix Definitions')
        yaml_conf.yaml_set_comment_before_after_key('monitors',
                                                    before='\n')
        yaml_conf.yaml_set_comment_before_after_key('monitors',
                                                    before='Start of Monitor Definitions')
        yaml_conf.yaml_set_comment_before_after_key('asns',
                                                    before='End of Monitor Definitions')
        yaml_conf.yaml_set_comment_before_after_key('asns',
                                                    before='\n')
        yaml_conf.yaml_set_comment_before_after_key('asns',
                                                    before='Start of ASN Definitions')
        yaml_conf.yaml_set_comment_before_after_key('rules',
                                                    before='End of ASN Definitions')
        yaml_conf.yaml_set_comment_before_after_key('rules',
                                                    before='\n')
        yaml_conf.yaml_set_comment_before_after_key('rules',
                                                    before='Start of Rule Definitions')
        # dump conf
        yaml.dump(yaml_conf, f)

        # end comments
        f.write('# End of Rule Definitions\n')
