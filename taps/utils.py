import os
import copy
from ipaddress import ip_network as str2ip

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')

def decompose_path(path):

    # first do an ultra-fast check if the path is a normal one
    # (simple sequence of ASNs)
    str_path = ' '.join(map(str, path))
    if '{' not in str_path and '[' not in str_path and '(' not in str_path:
        return [path]

    # otherwise, check how to decompose
    decomposed_paths = []
    for hop in path:
        hop = str(hop)
        # AS-sets
        if '{' in hop:
            decomposed_hops = hop.lstrip('{').rstrip('}').split(',')
        # AS Confederation Set
        elif '[' in hop:
            decomposed_hops = hop.lstrip('[').rstrip(']').split(',')
        # AS Sequence Set
        elif '(' in hop or ')' in hop:
            decomposed_hops = hop.lstrip('(').rstrip(')').split(',')
        # simple ASN
        else:
            decomposed_hops = [hop]
        new_paths = []
        if len(decomposed_paths) == 0:
            for dec_hop in decomposed_hops:
                new_paths.append([dec_hop])
        else:
            for prev_path in decomposed_paths:
                if '(' in hop or ')' in hop:
                    new_path = prev_path + decomposed_hops
                    new_paths.append(new_path)
                else:
                    for dec_hop in decomposed_hops:
                        new_path = prev_path + [dec_hop]
                        new_paths.append(new_path)
        decomposed_paths = new_paths
    return decomposed_paths

def normalize_msg_path(msg):
    msgs = []
    path = msg['path']
    if isinstance(path, list):
        dec_paths = decompose_path(path)
        if len(dec_paths) < 2:
            msgs = [msg]
        else:
            for dec_path in dec_paths:
                copied_msg = copy.deepcopy(msg)
                copied_msg['path'] = list(map(int, dec_path))
                copied_msg['orig_path'] = path
                msgs.append(copied_msg)
    else:
        msgs = [msg]

    return msgs

def mformat_validator(msg):

    mformat_fields = [
        'key',
        'service',
        'type',
        'prefix',
        'path',
        'communities',
        'timestamp'
    ]
    type_values = ['A', 'W']
    community_keys = set(['asn', 'value'])

    def valid_msg(msg):
        if not isinstance(msg, dict):
            return False
        return True

    def valid_fields(msg):
        if any(field not in msg for field in mformat_fields):
            return False
        return True

    def valid_prefix(msg):
        try:
            str2ip(msg['prefix'])
        except:
            return False
        return True

    def valid_service(msg):
        if not isinstance(msg['service'], str):
            return False
        return True

    def valid_type(msg):
        if msg['type'] not in type_values:
            return False
        return True

    def valid_path(msg):
        if msg['type'] == 'A' and not isinstance(msg['path'], list):
            return False
        return True

    def valid_communities(msg):
        if not isinstance(msg['communities'], list):
            return False
        for comm in msg['communities']:
            if not isinstance(comm, dict):
                return False
            if len(community_keys - set(comm.keys())) != 0:
                return False
        return True

    def valid_timestamp(msg):
        if not (isinstance(msg['timestamp'], float) or isinstance(msg['timestamp'], int)):
            return False
        return True

    def valid_generator(msg):
        yield valid_msg
        yield valid_fields
        yield valid_prefix
        yield valid_service
        yield valid_type
        yield valid_path
        yield valid_communities
        yield valid_timestamp

    for func in valid_generator(msg):
        if not func(msg):
            return False

    return True
