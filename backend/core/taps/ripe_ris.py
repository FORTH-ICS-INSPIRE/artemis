import argparse
from copy import deepcopy
from ipaddress import ip_network as str2ip
import json
from kombu import Connection, Producer, Exchange
import os
from utils import mformat_validator, normalize_msg_path, key_generator, RABBITMQ_URI, get_logger, is_subnet_of
import websocket

log = get_logger()
update_to_type = {
    'announcements': 'A',
    'withdrawals': 'W'
}
update_types = [
    'announcements',
    'withdrawals'
]


def normalize_ripe_ris(msg, conf_prefix):
    msgs = []
    if isinstance(msg, dict):
        msg['key'] = None  # initial placeholder before passing the validator
        if 'community' in msg:
            msg['communities'] = [{'asn': comm[0], 'value': comm[1]}
                                  for comm in msg['community']]
            del msg['community']
        if 'host' in msg:
            msg['service'] = 'ripe-ris|' + msg['host']
            del msg['host']
        if 'peer_asn' in msg:
            msg['peer_asn'] = int(msg['peer_asn'])
        if 'path' not in msg:
            msg['path'] = []
        if 'timestamp' in msg:
            msg['timestamp'] = float(msg['timestamp'])
        if 'type' in msg:
            del msg['type']
        if 'announcements' in msg and 'withdrawals' in msg:
            # need 2 separate messages
            # one for announcements
            msg_ann = deepcopy(msg)
            msg_ann['type'] = update_to_type['announcements']
            prefixes = []
            for element in msg_ann['announcements']:
                if 'prefixes' in element:
                    prefixes.extend(element['prefixes'])
            for prefix in prefixes:
                try:
                    if is_subnet_of(str2ip(prefix), conf_prefix):
                        new_msg = deepcopy(msg_ann)
                        new_msg['prefix'] = prefix
                        del new_msg['announcements']
                        msgs.append(new_msg)
                except Exception:
                    log.exception('exception')
            # one for withdrawals
            msg_wit = deepcopy(msg)
            msg_wit['type'] = update_to_type['withdrawals']
            msg_wit['path'] = []
            msg_wit['communities'] = []
            prefixes = msg_wit['withdrawals']
            for prefix in prefixes:
                try:
                    if is_subnet_of(str2ip(prefix), conf_prefix):
                        new_msg = deepcopy(msg_wit)
                        new_msg['prefix'] = prefix
                        del new_msg['withdrawals']
                        msgs.append(new_msg)
                except Exception:
                    log.exception('exception')
        else:
            for update_type in update_types:
                if update_type in msg:
                    msg['type'] = update_to_type[update_type]
                    prefixes = []
                    for element in msg[update_type]:
                        if update_type == 'announcements':
                            if 'prefixes' in element:
                                prefixes.extend(element['prefixes'])
                        elif update_type == 'withdrawals':
                            prefixes.append(element)
                    for prefix in prefixes:
                        try:
                            if is_subnet_of(str2ip(prefix), conf_prefix):
                                new_msg = deepcopy(msg)
                                new_msg['prefix'] = prefix
                                del new_msg[update_type]
                                msgs.append(new_msg)
                        except Exception:
                            log.exception('exception')
    return msgs


def parse_ripe_ris(connection, prefix, host):
    exchange = Exchange(
        'bgp-update',
        channel=connection,
        type='direct',
        durable=False)
    exchange.declare()

    conf_prefix = None
    try:
        conf_prefix = str2ip(prefix)
    except Exception:
        log.exception('exception')

    ris_suffix = os.getenv('RIS_ID', 'my_as')
    ws = websocket.WebSocket()
    ws.connect("wss://ris-live.ripe.net/v1/ws/?client=artemis-as{}".format(ris_suffix))
    params = {
        "host": host,
        "type": "UPDATE",
        "prefix": prefix,
        "moreSpecific": True,
        "lessSpecific": False,
        "socketOptions": {
            "includeRaw": False
        }
    }

    ws.send(json.dumps({
        "type": "ris_subscribe",
        "data": params
    }))

    for data in ws:
        try:
            parsed = json.loads(data)
            msg = parsed["data"]
            producer = Producer(connection)
            norm_ris_msgs = normalize_ripe_ris(msg, conf_prefix)
            for norm_ris_msg in norm_ris_msgs:
                if mformat_validator(norm_ris_msg):
                    norm_path_msgs = normalize_msg_path(norm_ris_msg)
                    for norm_path_msg in norm_path_msgs:
                        key_generator(norm_path_msg)
                        log.debug(norm_path_msg)
                        producer.publish(
                            norm_path_msg,
                            exchange=exchange,
                            routing_key='update',
                            serializer='json'
                        )
                else:
                    log.warning('Invalid format message: {}'.format(msg))
        except Exception:
            log.exception('exception')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RIPE RIS Monitor')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-r', '--host', type=str, dest='host', default=None,
                        help='Directory with csvs to read')

    args = parser.parse_args()
    prefix = args.prefix
    host = args.host

    try:
        with Connection(RABBITMQ_URI) as connection:
            parse_ripe_ris(connection, prefix, host)
    except Exception:
        log.exception('exception')
    except KeyboardInterrupt:
        pass
