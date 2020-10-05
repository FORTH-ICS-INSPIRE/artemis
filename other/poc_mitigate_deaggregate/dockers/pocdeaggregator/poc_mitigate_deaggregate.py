#!/usr/bin/env python
import argparse
import logging
import time
from ipaddress import ip_network as str2ip

import ujson as json
from socketIO_client import BaseNamespace
from socketIO_client import SocketIO


def get_logger():
    logging_format = (
        "%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s"
    )
    logging.basicConfig(format=logging_format, level=logging.INFO)
    return logging


# Sample call: python poc_mitigate_deaggregate.py -i '{"key":"123","prefix":"10.0.0.0/23"}'
parser = argparse.ArgumentParser(description="test ARTEMIS mitigation via deggregation")
parser.add_argument(
    "-i",
    "--info_hijack",
    dest="info_hijack",
    type=str,
    help="hijack event information",
    required=True,
)
parser.add_argument(
    "-e",
    "--exahost",
    dest="exa_host",
    type=str,
    help="ExaBGP host (optional)",
    default=None,
)
args = parser.parse_args()

log = get_logger()

# info_hijack = {
#     "key": <hijack_key>,
#     "prefix": <prefix>
# }
try:
    info_hijack = json.loads(args.info_hijack)
    # TODO: use proper logger!
    log.info("Preparing to mitigate via deaggregation hijack {}".format(info_hijack))
    hijacked_prefix = str2ip(info_hijack["prefix"])
    hijacked_prefix_len = hijacked_prefix.prefixlen
    deagg_len_threshold = 24
    if hijacked_prefix.version == 6:
        deagg_len_threshold = 64
    if hijacked_prefix_len < deagg_len_threshold:
        subnets = list(hijacked_prefix.subnets())
        log.info("Subnets to announce: {}".format(subnets))
        # TODO: send BGP message via exaBGP
        if args.exa_host is not None:
            sio = SocketIO("http://" + args.exa_host, namespace=BaseNamespace)
            for subnet in subnets:
                msg = {
                    "type": "A",
                    # TODO: make this configurable
                    "communities": [],
                    "timestamp": float(time.time()),
                    # TODO: make this configurable
                    "path": [],
                    "prefix": subnet,
                    # TODO: make this configurable
                    "peer_asn": None,
                }
                sio.emit(msg)
            sio.disconnect()
    else:
        log.info(
            "Cannot deaggregate a prefix more specific than /{}".format(
                deagg_len_threshold - 1
            )
        )
except Exception as e:
    log.error("Exception occurred while deaggregating")
    log.error(e)
