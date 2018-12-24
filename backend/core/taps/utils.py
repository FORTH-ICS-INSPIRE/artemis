import os
import copy
import pickle
import hashlib
from ipaddress import ip_network as str2ip
import yaml
import logging
import logging.config


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')


def get_logger(path='/etc/artemis/logging.yaml'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger('taps_logger')
        log.info('Loaded configuration from {}'.format(path))
    else:
        FORMAT = '%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s'
        logging.basicConfig(format=FORMAT, level=logging.INFO)
        log = logging
        log.info('Loaded default configuration')
    return log


def key_generator(msg):
    msg['key'] = hashlib.md5(pickle.dumps([
        msg['prefix'],
        msg['path'],
        msg['type'],
        msg['timestamp'],
        msg['peer_asn']
    ])).hexdigest()


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
        if not decomposed_paths:
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
    msg['orig_path'] = None
    if isinstance(path, list):
        dec_paths = decompose_path(path)
        if not dec_paths:
            msg['path'] = []
            msgs = [msg]
        elif len(dec_paths) == 1:
            msg['path'] = list(map(int, dec_paths[0]))
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
        'service',
        'type',
        'prefix',
        'path',
        'communities',
        'timestamp',
        'peer_asn'
    ]
    type_values = {'A', 'W'}
    community_keys = {'asn', 'value'}

    optional_fields_init = {
        'communities': []
    }

    def valid_dict(msg):
        if not isinstance(msg, dict):
            return False
        return True

    def add_optional_fields(msg):
        for field in optional_fields_init:
            if field not in msg:
                msg[field] = optional_fields_init[field]

    def valid_fields(msg):
        if any(field not in msg for field in mformat_fields):
            return False
        return True

    def valid_prefix(msg):
        try:
            str2ip(msg['prefix'])
        except BaseException:
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
            if (community_keys - set(comm.keys())):
                return False
        return True

    def valid_timestamp(msg):
        if not isinstance(msg['timestamp'], float):
            return False
        return True

    def valid_peer_asn(msg):
        if not isinstance(msg['peer_asn'], int):
            return False
        return True

    def valid_generator(msg):
        yield valid_fields
        yield valid_prefix
        yield valid_service
        yield valid_type
        yield valid_path
        yield valid_communities
        yield valid_timestamp
        yield valid_peer_asn

    if not valid_dict(msg):
        return False

    add_optional_fields(msg)

    for func in valid_generator(msg):
        if not func(msg):
            return False

    return True
