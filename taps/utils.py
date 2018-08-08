from ipaddress import ip_network as str2ip
import os
import pickle
import hashlib

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')

def key_generator(msg):
    msg['key'] = hashlib.md5(pickle.dumps([
        msg['prefix'],
        msg['path'],
        msg['type'],
        msg['service'],
        msg['timestamp']
    ])).hexdigest()


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
