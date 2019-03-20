import argparse
import json
import os
import time
from copy import deepcopy

import radix
import requests
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from utils import get_logger
from utils import key_generator
from utils import mformat_validator
from utils import normalize_msg_path
from utils import RABBITMQ_URI

log = get_logger()
update_to_type = {"announcements": "A", "withdrawals": "W"}
update_types = ["announcements", "withdrawals"]


def normalize_ripe_ris(msg, prefix_tree):
    msgs = []
    if isinstance(msg, dict):
        msg["key"] = None  # initial placeholder before passing the validator
        if "community" in msg:
            msg["communities"] = [
                {"asn": comm[0], "value": comm[1]} for comm in msg["community"]
            ]
            del msg["community"]
        if "host" in msg:
            msg["service"] = "ripe-ris|" + msg["host"]
            del msg["host"]
        if "peer_asn" in msg:
            msg["peer_asn"] = int(msg["peer_asn"])
        if "path" not in msg:
            msg["path"] = []
        if "timestamp" in msg:
            msg["timestamp"] = float(msg["timestamp"])
        if "type" in msg:
            del msg["type"]
        if "raw" in msg:
            del msg["raw"]
        if "origin" in msg:
            del msg["origin"]
        if "id" in msg:
            del msg["id"]
        if "announcements" in msg and "withdrawals" in msg:
            # need 2 separate messages
            # one for announcements
            msg_ann = deepcopy(msg)
            msg_ann["type"] = update_to_type["announcements"]
            prefixes = []
            for element in msg_ann["announcements"]:
                if "prefixes" in element:
                    prefixes.extend(element["prefixes"])
            for prefix in prefixes:
                try:
                    if prefix_tree.search_best(prefix):
                        new_msg = deepcopy(msg_ann)
                        new_msg["prefix"] = prefix
                        del new_msg["announcements"]
                        msgs.append(new_msg)
                except Exception:
                    log.exception("exception")
            # one for withdrawals
            msg_wit = deepcopy(msg)
            msg_wit["type"] = update_to_type["withdrawals"]
            msg_wit["path"] = []
            msg_wit["communities"] = []
            prefixes = msg_wit["withdrawals"]
            for prefix in prefixes:
                try:
                    if prefix_tree.search_best(prefix):
                        new_msg = deepcopy(msg_wit)
                        new_msg["prefix"] = prefix
                        del new_msg["withdrawals"]
                        msgs.append(new_msg)
                except Exception:
                    log.exception("exception")
        else:
            for update_type in update_types:
                if update_type in msg:
                    msg["type"] = update_to_type[update_type]
                    prefixes = []
                    for element in msg[update_type]:
                        if update_type == "announcements":
                            if "prefixes" in element:
                                prefixes.extend(element["prefixes"])
                        elif update_type == "withdrawals":
                            prefixes.append(element)
                    for prefix in prefixes:
                        try:
                            if prefix_tree.search_best(prefix):
                                new_msg = deepcopy(msg)
                                new_msg["prefix"] = prefix
                                del new_msg[update_type]
                                msgs.append(new_msg)
                        except Exception:
                            log.exception("exception")
    return msgs


def parse_ripe_ris(connection, prefixes, hosts):
    exchange = Exchange("bgp-update", channel=connection, type="direct", durable=False)
    exchange.declare()

    prefix_tree = radix.Radix()
    for prefix in prefixes:
        prefix_tree.add(prefix)

    ris_suffix = os.getenv("RIS_ID", "my_as")

    validator = mformat_validator()
    with Producer(connection) as producer:
        while True:
            try:
                events = requests.get(
                    "https://ris-live.ripe.net/v1/stream/?format=json&client=artemis-{}".format(
                        ris_suffix
                    ),
                    stream=True,
                )
                # http://docs.python-requests.org/en/latest/user/advanced/#streaming-requests
                iterator = events.iter_lines()
                next(iterator)
                for data in iterator:
                    try:
                        parsed = json.loads(data)
                        msg = parsed["data"]
                        # also check if ris host is in the configuration
                        if (
                            "type" in msg
                            and msg["type"] == "UPDATE"
                            and (not hosts or msg["host"] in hosts)
                        ):
                            norm_ris_msgs = normalize_ripe_ris(msg, prefix_tree)
                            for norm_ris_msg in norm_ris_msgs:
                                if validator.validate(norm_ris_msg):
                                    norm_path_msgs = normalize_msg_path(norm_ris_msg)
                                    for norm_path_msg in norm_path_msgs:
                                        key_generator(norm_path_msg)
                                        log.debug(norm_path_msg)
                                        producer.publish(
                                            norm_path_msg,
                                            exchange=exchange,
                                            routing_key="update",
                                            serializer="json",
                                        )
                                else:
                                    log.warning(
                                        "Invalid format message: {}".format(msg)
                                    )
                    except Exception:
                        log.exception("exception")
            except Exception:
                log.exception("server closed connection")
                time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RIPE RIS Monitor")
    parser.add_argument(
        "-p",
        "--prefix",
        type=str,
        dest="prefix",
        default=None,
        help="Prefix to be monitored",
    )
    parser.add_argument(
        "-r",
        "--hosts",
        type=str,
        dest="hosts",
        default=None,
        help="Directory with csvs to read",
    )

    args = parser.parse_args()
    prefix = args.prefix.split(",")
    hosts = args.hosts
    if hosts:
        hosts = set(hosts.split(","))

    try:
        with Connection(RABBITMQ_URI) as connection:
            parse_ripe_ris(connection, prefix, hosts)
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
