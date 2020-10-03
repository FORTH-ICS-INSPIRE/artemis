#!/usr/bin/env python
import argparse
from ipaddress import ip_network as str2ip

import ujson as json

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
args = parser.parse_args()

# info_hijack = {
#     "key": <hijack_key>,
#     "prefix": <prefix>
# }
try:
    info_hijack = json.loads(args.info_hijack)
    # TODO: use proper logger!
    print("Preparing to mitigate via deaggregation hijack {}".format(info_hijack))
    hijacked_prefix = str2ip(info_hijack["prefix"])
    hijacked_prefix_len = hijacked_prefix.prefixlen
    deagg_len_threshold = 24
    if hijacked_prefix.version == 6:
        deagg_len_threshold = 64
    if hijacked_prefix_len < deagg_len_threshold:
        subnets = list(hijacked_prefix.subnets())
        print("Subnets to announce: {}".format(subnets))
        # TODO: send BGP message via exaBGP
    else:
        print(
            "Cannot deaggregate a prefix more specific than /{}".format(
                deagg_len_threshold - 1
            )
        )
except Exception as e:
    print("Exception occurred while deaggregating")
    print(e)
