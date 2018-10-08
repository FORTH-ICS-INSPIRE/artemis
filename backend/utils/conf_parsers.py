import argparse
import glob
import os
import re
import ruamel.yaml
from datetime import datetime, timezone
from ipaddress import ip_network as str2ip
from pprint import pprint as pp

VALID_FORMAT_PARSERS = {
    1: lambda x: format_1_parser(x),
    2: lambda x: format_2_parser(x),
    3: lambda x: format_3_parser(x)
}

DEFAULT_MIT_ACTION = 'manual'


def extract_file_metadata(filepath):
    """
    TODO: COMMENT
    ASN_PEERNAME_FORMATNUMBER_YYYYMMDD_HHMM
    """
    filename = filepath.split('/')[-1]
    filename_elems = filename.split('_')
    try:
        peer_asn = int(filename_elems[0].lstrip('AS'))
        peer_name = str(filename_elems[1])
        format_number = int(filename_elems[2])
        time_struct = {
            'year': int(filename_elems[3][:4]),
            'month': int(filename_elems[3][4:6]),
            'day': int(filename_elems[3][6:8]),
            'hour': int(filename_elems[4][:2]),
            'minute': int(filename_elems[4][2:4])
        }
        file_metadata = {
            'peer_asn': peer_asn,
            'peer_name': peer_name,
            'format_number': format_number,
            'time': {
                'orig_time_struct': time_struct,
                'hour_timestamp': int(datetime(
                    time_struct['year'],
                    time_struct['month'],
                    time_struct['day'],
                    time_struct['hour']
                ).replace(tzinfo=timezone.utc).timestamp())
            }
        }
    except:
        return None
    return file_metadata


def parse_prefixes(filepath, format_number):
    """
    TODO: COMMENT
    """
    if format_number not in VALID_FORMAT_PARSERS.keys():
        return set()
    prefixes = VALID_FORMAT_PARSERS[format_number](filepath)

    return prefixes


def format_1_parser(filepath):
    """
    TODO: COMMENT
    """
    prefixes = set()
    return prefixes


def format_2_parser(filepath):
    """
    TODO: COMMENT
    """
    prefixes = set()

    with open(filepath, 'r') as f:
        for line in f:
            line = line.lstrip(' ')
            if line.startswith('Prefix'):
                continue
            elems = list(filter(None, [elem.strip() for elem in line.strip().split('  ')]))

            prefix = elems[0].lstrip(' *')
            as_path = elems[-1]
            if as_path != 'I':
                continue
            try:
                (netip, netmask) = prefix.split('/')
                str2ip(prefix)
            except:
                continue

            pp(prefix)
            prefixes.add(prefix)

    return prefixes

def format_3_parser(filepath):
    """
    TODO: COMMENT
    """
    prefixes = set()

    with open(filepath, 'r') as f:
        for line in f:
            if line.startswith('Network'):
                continue
            elems = list(filter(None, [elem.strip() for elem in line.strip().split('  ')]))

            prefix = elems[0]
            as_path = elems[-1]
            if as_path != 'i':
                continue
            try:
                (netip, netmask) = prefix.split('/')
                str2ip(prefix)
            except:
                continue

            prefixes.add(prefix)

    return prefixes


def create_prefix_defs(yaml_conf, prefixes):
    """
    TODO: COMMENT
    """
    yaml_conf['prefixes'] = ruamel.yaml.comments.CommentedMap()
    for prefix in prefixes:
        prefix_str = prefixes[prefix]
        yaml_conf['prefixes'][prefix_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['prefixes'][prefix_str].append(prefix)
        yaml_conf['prefixes'][prefix_str].yaml_set_anchor(prefix_str)


def create_monitor_defs(yaml_conf):
    """
    TODO: COMMENT
    """
    yaml_conf['monitors'] = ruamel.yaml.comments.CommentedMap()
    riperis = []
    for i in range(1, 24):
        if i < 10:
            riperis.append('rrc0{}'.format(i))
        else:
            riperis.append('rrc{}'.format(i))
    yaml_conf['monitors']['riperis'] = riperis
    yaml_conf['monitors']['bgpstreamlive'] = ['routeviews', 'ris']


def create_asn_defs(yaml_conf, asns):
    """
    TODO: COMMENT
    """
    yaml_conf['asns'] = ruamel.yaml.comments.CommentedMap()
    for asn in asns:
        asn_str = asns[asn]
        yaml_conf['asns'][asn_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['asns'][asn_str].append(asn)
        yaml_conf['asns'][asn_str].yaml_set_anchor(asn_str)


def create_rule_defs(yaml_conf, prefixes, asns, prefix_pols):
    """
    TODO: COMMENT
    """
    yaml_conf['rules'] = ruamel.yaml.comments.CommentedSeq()
    for prefix in prefix_pols:
        pol_dict = ruamel.yaml.comments.CommentedMap()
        prefix_str = prefixes[prefix]
        pol_dict['prefixes'] = [yaml_conf['prefixes'][prefix_str]]
        pol_dict['origin_asns'] = [yaml_conf['asns'][asns[asn]]
                                   for asn in prefix_pols[prefix]['origins']],
        pol_dict['neighbors'] = [yaml_conf['asns'][asns[asn]]
                                 for asn in prefix_pols[prefix]['neighbors']],
        pol_dict['mitigation'] = 'manual'
        yaml_conf['rules'].append(pol_dict)


def generate_config_yml(prefixes, asns, prefix_pols, yml_file=None):
    """
    TODO: COMMENT
    """
    with open(yml_file, 'w') as f:

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
        create_rule_defs(yaml_conf, prefixes, asns, prefix_pols)

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

if __name__=='__main__':
    parser = argparse.ArgumentParser(
        description="generate ARTEMIS configuration from custom_files")
    parser.add_argument(
        '-d',
        '--dir',
        dest='dir',
        type=str,
        help='directory with configurations',
        required=True
    )
    parser.add_argument(
        '-o',
        '--origin',
        dest='origin_asn',
        type=int,
        help='origin asn',
        required=True
    )
    parser.add_argument(
        '-c',
        '--conf',
        dest='conf_dir',
        type=str,
        help='output config dir to store the retrieved information',
        required=True)
    args = parser.parse_args()

    configurations = {}

    in_dir = args.dir.rstrip('/')
    conf_dir = args.conf_dir.rstrip('/')
    if not os.path.isdir(conf_dir):
        os.mkdir(conf_dir)
    created_conf_timestamps = set()
    for conf_filepath in glob.glob('{}/config_*.yaml'.format(conf_dir)):
        conf_timestamp = int(conf_filepath.split('/')[-1].split('_')[-1].split('.yaml')[0])
        created_conf_timestamps.add(conf_timestamp)

    for filepath in glob.glob('{}/*'.format(in_dir)):
        file_metadata = extract_file_metadata(filepath)
        if file_metadata is not None:
            hour_timestamp = file_metadata['time']['hour_timestamp']

            # UNCOMMENT IN PRODUCTION TO AVOID REPARSING THE SAME INFO!
            #if hour_timestamp in created_conf_timestamps:
            #   continue

            if hour_timestamp not in configurations:
                configurations[hour_timestamp] = {
                    'asns': {},
                    'prefixes': {},
                    'prefix_pols': {}
                }

            configurations[hour_timestamp]['asns'][args.origin_asn] = 'origin'
            configurations[hour_timestamp]['asns'][file_metadata['peer_asn']] = file_metadata['peer_name']
            this_peer_prefixes = parse_prefixes(filepath, file_metadata['format_number'])
            for prefix in this_peer_prefixes:
                configurations[hour_timestamp]['prefixes'][prefix] = str(prefix)
                if prefix not in configurations[hour_timestamp]:
                    configurations[hour_timestamp]['prefix_pols'][prefix] = {
                        'origins': set(),
                        'neighbors': set()
                    }
                    configurations[hour_timestamp]['prefix_pols'][prefix]['origins'].add(args.origin_asn)
                    configurations[hour_timestamp]['prefix_pols'][prefix]['neighbors'].add(file_metadata['peer_asn'])

    for hour_timestamp in configurations:
        yml_file = '{}/config_{}.yaml'.format(conf_dir, hour_timestamp)
        generate_config_yml(
            configurations[hour_timestamp]['prefixes'],
            configurations[hour_timestamp]['asns'],
            configurations[hour_timestamp]['prefix_pols'],
            yml_file=yml_file)

