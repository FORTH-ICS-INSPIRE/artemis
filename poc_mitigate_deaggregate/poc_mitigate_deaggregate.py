#!/usr/bin/env python
import argparse
import json
import logging
from ipaddress import ip_network as str2ip

from socketIO_client import BaseNamespace
from socketIO_client import SocketIO


EXA_ROUTE_COMMAND_HOST = "exabgproutecommander:5000"


log = logging.getLogger("artemis")
log.setLevel(logging.DEBUG)
# create a file handler
handler = logging.FileHandler("/var/log/artemis/mitigation.log")
handler.setLevel(logging.DEBUG)
# create a logging format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
# add the handlers to the logger
log.addHandler(handler)


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
    "-p",
    "--announce_prefixes",
    dest="announce_prefixes",
    type=str,
    help="prefixes to be announced for mitigation",
    required=False,
)
args = parser.parse_args()

# info_hijack = {
#     "key": <hijack_key>,
#     "prefix": <prefix>
# }
try:
    info_hijack = json.loads(args.info_hijack)
    announce_prefixes = []
    if args.announce_prefixes:
        announce_prefixes = json.loads(args.announce_prefixes)

    log.info("Preparing to mitigate via deaggregation hijack {}".format(info_hijack))
    hijacked_prefix = str2ip(info_hijack["prefix"])
    hijacked_prefix_len = hijacked_prefix.prefixlen
    deagg_len_threshold = 24
    if hijacked_prefix.version == 6:
        deagg_len_threshold = 64
    if hijacked_prefix_len < deagg_len_threshold:
        subnets = list(map(str, list(hijacked_prefix.subnets())))
        log.info("Subnets to announce: {}".format(subnets))
        if len(announce_prefixes) > 0:
            subnets = announce_prefixes

        for subnet in subnets:
            exa_command = "announce route {} next-hop self".format(subnet)
            sio = SocketIO("http://" + EXA_ROUTE_COMMAND_HOST, namespace=BaseNamespace)
            sio.connect()
            sio.emit("route_command", {"command": exa_command})
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
