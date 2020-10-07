#!/usr/bin/env python
import argparse
import json
import logging
from ipaddress import ip_network as str2ip

EXA_COMMAND_LIST_FILE = "exa_mitigation_commands.json"


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
args = parser.parse_args()

log = get_logger()

# info_hijack = {
#     "key": <hijack_key>,
#     "prefix": <prefix>
# }
try:
    info_hijack = json.loads(args.info_hijack)
    log.info("Preparing to mitigate via deaggregation hijack {}".format(info_hijack))
    hijacked_prefix = str2ip(info_hijack["prefix"])
    hijacked_prefix_len = hijacked_prefix.prefixlen
    deagg_len_threshold = 24
    if hijacked_prefix.version == 6:
        deagg_len_threshold = 64
    if hijacked_prefix_len < deagg_len_threshold:
        subnets = list(map(str, list(hijacked_prefix.subnets())))
        log.info("Subnets to announce: {}".format(subnets))
        exa_command_list = []
        for subnet in subnets:
            exa_command_list.append("announce route {} next-hop self".format(subnet))
        with open(EXA_COMMAND_LIST_FILE, "w") as f:
            json.dump(exa_command_list, f)
    else:
        log.info(
            "Cannot deaggregate a prefix more specific than /{}".format(
                deagg_len_threshold - 1
            )
        )
except Exception as e:
    log.error("Exception occurred while deaggregating")
    log.error(e)
