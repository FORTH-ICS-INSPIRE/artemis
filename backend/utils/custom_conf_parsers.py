import argparse
import glob
import json
import os
import re
import ruamel.yaml
import shutil
from datetime import datetime, timezone
from itertools import chain, combinations
from ipaddress import ip_network as str2ip
import requests
from typing import Set

VALID_FORMAT_PARSERS = {
    1: lambda x: format_1_parser(x[0], x[1]),
    2: lambda x: format_2_parser(x[0], x[1]),
    3: lambda x: format_3_parser(x[0], x[1])
}

DEFAULT_MIT_ACTION = 'manual'


def powerset(iterable):
    """
    Auxiliary function for the generation of powersets (not used for now)
    powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)
    """
    xs = list(iterable)
    # note we return an iterator rather than a list
    return chain.from_iterable(combinations(xs, n) for n in range(len(xs) + 1))


def fetch_BIX_bgp_summary() -> Set:
    """
    Fetches all ASes that are visible through BIX routeservers.
    """

    res = requests.get('http://lg.bix.bg/')
    rs_list = set(re.findall('<OPTION VALUE=".*"> (.*)', res.text))

    as_list = set()
    for rs in rs_list:
        url = 'http://lg.bix.bg/?query=summary&addr=&router={}'.format(rs)
        # print('Requesting BGP Summary from {}'.format(rs))
        res = requests.get(url)
        as_list.update(set(re.findall('(?:AS)([0-9]+)', res.text)))
    return as_list


def fetch_DECIX_bgp_summary() -> Set:
    """
    Fetches all ASes that are visible through DECIX routeservers.
    """
    res = requests.get('https://lg.fra.de-cix.net/')
    rs_list = set(re.findall('<option value=\'(.*)\'>.*</option>', res.text))

    payload = {
        'query': 'show ip bgp summary',
        'tab': 'bgp_summary',
        'submit': 'Submit'
    }

    as_list = set()
    for rs in rs_list:
        url = 'https://lg.fra.de-cix.net/'
        # print('Requesting BGP Summary from {}'.format(rs))
        payload['routeserver'] = rs
        res = requests.post(url, data=payload)

        start = res.text.rfind('------------------------------------------------------------------------------------')
        end = res.text.find('Total number of neighbors')

        info = set(filter(None, res.text[start:end].split('\n')[1:]))
        for line in info:
            try:
                as_list.add(line.split()[1])
            except Exception:
                pass

    return as_list


def fetch_AMSIX_bgp_summary() -> Set:
    """
    Fetches all ASes that are visible through AMSIX routeservers.
    """
    res = requests.get('https://my.ams-ix.net/api/v1/members.json')

    as_list = set()
    for member in res.json().get('member_list', []):
        asnum = member['asnum']
        public = False
        for connection in member.get('connection_list', []):
            for vlan in connection.get('vlan_list', []):
                if vlan.get('ipv4', {}).get('routeserver', False):
                    as_list.add(asnum)
                    public = True
                if vlan.get('ipv6', {}).get('routeserver', False):
                    as_list.add(asnum)
                    public = True
                if public:
                    break
            if public:
                break
    return as_list


def extract_file_metadata(filepath):
    """
    Title format: ASN_PEERNAME_FORMATNUMBER_YYYYMMDD_HHMM
    This functions extracts the needed metadata from this filename
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
    except BaseException:
        return None
    return file_metadata


def parse_file(filepath, format_number, origin):
    """
    Dispatcher function for selecting the proper format to parse
    """
    if format_number not in VALID_FORMAT_PARSERS.keys():
        return set()
    prefixes = VALID_FORMAT_PARSERS[format_number]((filepath, origin))
    return prefixes


def format_1_parser(filepath, origin):
    """
    Parse format number 2:
    <prefix> is advertised to <ip>
        aspath: <list_of_ints>
    Note that the origin is needed to determine origination from the ARTEMIS tester.
    (TODO: make this a list if multiple ASNs --> not important at this stage)
    """
    prefixes = set()
    with open(filepath, 'r') as f:
        cur_prefix = None
        for line in f:
            line = line.lstrip(' ').strip('')
            prefix_regex = re.match(
                '(.*)\s*is\s*advertised.*', line)
            if prefix_regex:
                prefix = prefix_regex.group(1).strip(' ')
                try:
                    (netip, netmask) = prefix.split('/')
                    str2ip(prefix)
                except BaseException:
                    continue
                    cur_prefix = None
                cur_prefix = prefix
            else:
                as_path_regex = re.match('aspath\:\s+(.*)', line)
                if as_path_regex:
                    as_path_list = as_path_regex.group(1).split(' ')
                    assert len(as_path_list) > 0
                    if str(as_path_list[-1]) != str(origin):
                        cur_prefix = None
                        continue
                    prefixes.add(cur_prefix)
    return prefixes


def format_2_parser(filepath, origin):
    """
    Parse format number 2:
      Prefix		  Nexthop	       MED     Lclpref    AS path
    * <prefix>        <Self|ip>                0         <list of strings, can end with I|?>
    Note that the origin is needed to determine origination from the ARTEMIS tester.
    (TODO: make this a list if multiple ASNs --> not important at this stage)
    """
    prefixes = set()
    with open(filepath, 'r') as f:
        for line in f:
            line = line.lstrip(' ')
            if line.startswith('Prefix'):
                continue
            elems = list(filter(None, [elem.strip()
                                       for elem in line.strip().split('  ')]))

            prefix = elems[0].lstrip(' *')
            as_path = elems[-1]
            if not as_path.endswith('i') and not as_path.endswith(
                    'I') and not as_path.endswith(str(origin)):
                continue
            as_path_list = as_path.split(' ')
            if len(as_path_list) > 1:
                if str(as_path_list[-2]).strip('[]') != str(origin):
                    continue
            try:
                (netip, netmask) = prefix.split('/')
                str2ip(prefix)
            except BaseException:
                continue
            prefixes.add(prefix)
    return prefixes


def format_3_parser(filepath, origin):
    """
    Parse format number 3:
    Network             Next Hop        Metric     LocPrf     Path
    <prefix>            <ip>                                  <list of strings, can end with i|?>
    Note that the origin is needed to determine origination from the ARTEMIS tester.
    (TODO: make this a list if multiple ASNs --> not important at this stage)
    """
    prefixes = set()
    with open(filepath, 'r') as f:
        for line in f:
            line = line.lstrip(' ')
            if line.startswith('Network'):
                continue
            elems = list(filter(None, [elem.strip()
                                       for elem in line.strip().split('  ')]))
            prefix = elems[0]
            as_path = elems[-1]
            if not as_path.endswith('i') and not as_path.endswith(
                    'I') and not as_path.endswith(str(origin)):
                continue
            as_path_list = as_path.split(' ')
            if len(as_path_list) > 1:
                if str(as_path_list[-2]).strip('[]') != str(origin):
                    continue
            try:
                (netip, netmask) = prefix.split('/')
                str2ip(prefix)
            except BaseException:
                continue
            prefixes.add(prefix)
    return prefixes


def create_prefix_defs(yaml_conf, prefixes):
    """
    Create separate prefix definitions for the ARTEMIS conf file
    """
    prefix_to_str = {}
    yaml_conf['prefixes'] = ruamel.yaml.comments.CommentedMap()
    for prefix in sorted(prefixes):
        prefix_str = prefixes[prefix]
        prefix_to_str[prefix] = prefix_str
        yaml_conf['prefixes'][prefix_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['prefixes'][prefix_str].append(prefix)
        yaml_conf['prefixes'][prefix_str].yaml_set_anchor(prefix_str)


def create_monitor_defs(yaml_conf):
    """
    Create separate monitor definitions for the ARTEMIS conf file
    """
    yaml_conf['monitors'] = ruamel.yaml.comments.CommentedMap()
    yaml_conf['monitors']['riperis'] = ['']
    yaml_conf['monitors']['bgpstreamlive'] = ['routeviews', 'ris']
    yaml_conf['monitors']['betabmp'] = ['betabmp']


def create_asn_defs(yaml_conf, asns):
    """
    Create separate ASN definitions for the ARTEMIS conf file
    """
    yaml_conf['asns'] = ruamel.yaml.comments.CommentedMap()
    asn_groups = set()
    for asn in sorted(asns):
        asn_group = asns[asn][1]
        if asn_group is not None:
            asn_groups.add(asn_group)
    asn_groups = list(asn_groups)
    for asn_group in sorted(asn_groups):
        yaml_conf['asns'][asn_group] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf['asns'][asn_group].yaml_set_anchor(asn_group)
    for asn in sorted(asns):
        asn_str = asns[asn][0]
        asn_group = asns[asn][1]
        if asn_group is None:
            yaml_conf['asns'][asn_str] = ruamel.yaml.comments.CommentedSeq()
            yaml_conf['asns'][asn_str].append(asn)
            yaml_conf['asns'][asn_str].yaml_set_anchor(asn_str)
        else:
            yaml_conf['asns'][asn_group].append(asn)


def create_rule_defs(yaml_conf, prefixes, asns, prefix_pols):
    """
    Create grouped rule definitions for the ARTEMIS conf file
    """
    yaml_conf['rules'] = ruamel.yaml.comments.CommentedSeq()

    # first derive the prefix rule groups
    # (i.e., which prefixes have the same origin and neighbor)
    prefixes_per_orig_neighb_group = {}
    for prefix in sorted(prefix_pols):
        origin_asns = sorted(list(prefix_pols[prefix]['origins']))
        neighbors = sorted(list(prefix_pols[prefix]['neighbors']))
        key = (json.dumps(origin_asns), json.dumps(neighbors))
        if key not in prefixes_per_orig_neighb_group:
            prefixes_per_orig_neighb_group[key] = set()
        prefixes_per_orig_neighb_group[key].add(prefix)

    # then form the actual rules
    for key in sorted(prefixes_per_orig_neighb_group):
        pol_dict = ruamel.yaml.comments.CommentedMap()
        origin_asns = json.loads(key[0])
        neighbors = json.loads(key[1])
        pol_dict['prefixes'] = ruamel.yaml.comments.CommentedSeq()
        for prefix in sorted(prefixes_per_orig_neighb_group[key]):
            pol_dict['prefixes'].append(
                yaml_conf['prefixes'][prefixes[prefix]])
        pol_dict['origin_asns'] = []
        origin_groups = set()
        for asn in origin_asns:
            asn_str = asns[asn][0]
            asn_group = asns[asn][1]
            if asn_group is not None:
                if asn_group not in origin_groups:
                    pol_dict['origin_asns'].append(yaml_conf['asns'][asn_group])
                    origin_groups.add(asn_group)
            else:
                pol_dict['origin_asns'].append(yaml_conf['asns'][asn_str])
        pol_dict['neighbors'] = []
        neighbor_groups = set()
        for asn in neighbors:
            asn_str = asns[asn][0]
            asn_group = asns[asn][1]
            if asn_group is not None:
                if asn_group not in neighbor_groups:
                    pol_dict['neighbors'].append(yaml_conf['asns'][asn_group])
                    neighbor_groups.add(asn_group)
            else:
                pol_dict['neighbors'].append(yaml_conf['asns'][asn_str])
        pol_dict['mitigation'] = DEFAULT_MIT_ACTION
        yaml_conf['rules'].append(pol_dict)


def generate_config_yml(prefixes, asns, prefix_pols, yml_file=None):
    """
    write the config.yaml file content
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="generate ARTEMIS configuration from custom_files")
    parser.add_argument(
        '-d',
        '--dir',
        dest='dir',
        type=str,
        help='directory with raw files',
        required=True
    )
    parser.add_argument(
        '-o',
        '--origin',
        dest='origin_asn',
        type=int,
        help='origin asn (TODO: list in the future)',
        required=True
    )
    parser.add_argument(
        '-c',
        '--conf',
        dest='conf_dir',
        type=str,
        help='output config dir to store the extracted timestamped configurations',
        required=True)
    args = parser.parse_args()

    configurations = {}

    in_dir = args.dir.rstrip('/')
    conf_dir = args.conf_dir.rstrip('/')
    if not os.path.isdir(conf_dir):
        os.mkdir(conf_dir)

    # scan all provided raw files
    for filepath in glob.glob('{}/*'.format(in_dir)):
        file_metadata = extract_file_metadata(filepath)
        if file_metadata is not None:
            hour_timestamp = file_metadata['time']['hour_timestamp']

            # create directory for putting raw files based on timestamp
            hour_timestamp_dir = '{}/{}'.format(in_dir, hour_timestamp)
            if not os.path.isdir(hour_timestamp_dir):
                os.mkdir(hour_timestamp_dir)

            # initialize current configurations
            if hour_timestamp not in configurations:
                configurations[hour_timestamp] = {
                    'asns': {},
                    'prefixes': {},
                    'prefix_pols': {}
                }

            # update current configurations
            # for asns, the first tuple element is the name and the second the group
            configurations[hour_timestamp]['asns'][args.origin_asn] = ('origin', None)
            configurations[hour_timestamp]['asns'][file_metadata['peer_asn']
                                                    ] = (file_metadata['peer_name'], None)
            this_peer_prefixes = parse_file(
                filepath, file_metadata['format_number'], args.origin_asn)
            for prefix in this_peer_prefixes:
                configurations[hour_timestamp]['prefixes'][prefix] = str(
                    prefix).replace('.', '_').replace('/', '-')
                if prefix not in configurations[hour_timestamp]['prefix_pols']:
                    configurations[hour_timestamp]['prefix_pols'][prefix] = {
                        'origins': set(),
                        'neighbors': set()
                    }
                configurations[hour_timestamp]['prefix_pols'][prefix]['origins'].add(
                    args.origin_asn)
                configurations[hour_timestamp]['prefix_pols'][prefix]['neighbors'].add(
                    file_metadata['peer_asn'])

            # move raw file into proper timestamp directory
            try:
                shutil.move(filepath, hour_timestamp_dir)
            except BaseException:
                # print("Could not move '{}'".format(filepath))
                pass

    # add ixp asn info, assuming that all prefixes are advertised at the IXPs
    bix_peers = fetch_BIX_bgp_summary() - {str(args.origin_asn)}
    decix_peers = fetch_DECIX_bgp_summary() - {str(args.origin_asn)}
    amsix_peers = fetch_AMSIX_bgp_summary() - {str(args.origin_asn)}
    peer_groups = {
        'BIX_RS_PEER': bix_peers,
        'DECIX_RS_PEER': decix_peers,
        'AMSIX_RS_PEER': amsix_peers
    }
    for peer_group in peer_groups:
        for asn in peer_groups[peer_group]:
            asn = int(asn)
            for hour_timestamp in configurations:
                if asn not in configurations[hour_timestamp]['asns']:
                    configurations[hour_timestamp]['asns'][asn] = ('{}_{}'.format(peer_group, asn), '{}S'.format(peer_group))
                    for prefix in configurations[hour_timestamp]['prefix_pols']:
                        if asn not in configurations[hour_timestamp]['prefix_pols'][prefix]['neighbors']:
                            configurations[hour_timestamp]['prefix_pols'][prefix]['neighbors'].add(asn)

    # scan all configurations
    for hour_timestamp in configurations:
        yml_file = '{}/config_{}.yaml'.format(conf_dir, hour_timestamp)
        generate_config_yml(
            configurations[hour_timestamp]['prefixes'],
            configurations[hour_timestamp]['asns'],
            configurations[hour_timestamp]['prefix_pols'],
            yml_file=yml_file)

    # select most recent configuration
    most_recent_timestamp = max(configurations)
    most_recent_config = '{}/config_{}.yaml'.format(conf_dir, most_recent_timestamp)
    assert os.path.isfile(most_recent_config)
    shutil.copy(most_recent_config, '{}/config.yaml'.format(conf_dir))
