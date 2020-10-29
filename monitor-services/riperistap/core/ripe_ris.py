import argparse
import os
import time
from copy import deepcopy

import pytricia
import redis
import requests
import ujson as json
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import key_generator
from artemis_utils import load_json
from artemis_utils import mformat_validator
from artemis_utils import normalize_msg_path
from artemis_utils import ping_redis
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import REDIS_PORT
from kombu import Connection
from kombu import Exchange
from kombu import Producer

log = get_logger()
update_to_type = {"announcements": "A", "withdrawals": "W"}
update_types = ["announcements", "withdrawals"]
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60


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
                ip_version = get_ip_version(prefix)
                try:
                    if prefix in prefix_tree[ip_version]:
                        new_msg = deepcopy(msg_ann)
                        new_msg["prefix"] = prefix
                        del new_msg["announcements"]
                        del new_msg["withdrawals"]
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
                ip_version = get_ip_version(prefix)
                try:
                    if prefix in prefix_tree[ip_version]:
                        new_msg = deepcopy(msg_wit)
                        new_msg["prefix"] = prefix
                        del new_msg["announcements"]
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
                        ip_version = get_ip_version(prefix)
                        try:
                            if prefix in prefix_tree[ip_version]:
                                new_msg = deepcopy(msg)
                                new_msg["prefix"] = prefix
                                del new_msg[update_type]
                                msgs.append(new_msg)
                        except Exception:
                            log.exception("exception")
    return msgs


def parse_ripe_ris(connection, prefixes_file, hosts):
    exchange = Exchange("bgp-update", channel=connection, type="direct", durable=False)
    exchange.declare()

    prefixes = load_json(prefixes_file)
    assert prefixes is not None
    prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
    for prefix in prefixes:
        ip_version = get_ip_version(prefix)
        prefix_tree[ip_version].insert(prefix, "")

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
                    timeout=10,
                )
                # http://docs.python-requests.org/en/latest/user/advanced/#streaming-requests
                iterator = events.iter_lines()
                next(iterator)
                for data in iterator:
                    try:
                        parsed = json.loads(data)
                        msg = parsed["data"]
                        if "type" in parsed and parsed["type"] == "ris_error":
                            log.error(msg)
                        # also check if ris host is in the configuration
                        elif (
                            "type" in msg
                            and msg["type"] == "UPDATE"
                            and (not hosts or msg["host"] in hosts)
                        ):
                            norm_ris_msgs = normalize_ripe_ris(msg, prefix_tree)
                            for norm_ris_msg in norm_ris_msgs:
                                redis.set(
                                    "ris_seen_bgp_update",
                                    "1",
                                    ex=int(
                                        os.getenv(
                                            "MON_TIMEOUT_LAST_BGP_UPDATE",
                                            DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                                        )
                                    ),
                                )
                                try:
                                    if validator.validate(norm_ris_msg):
                                        norm_path_msgs = normalize_msg_path(
                                            norm_ris_msg
                                        )
                                        for norm_path_msg in norm_path_msgs:
                                            key_generator(norm_path_msg)
                                            log.debug(norm_path_msg)
                                            producer.publish(
                                                norm_path_msg,
                                                exchange=exchange,
                                                routing_key="update",
                                                serializer="ujson",
                                            )
                                    else:
                                        log.warning(
                                            "Invalid format message: {}".format(msg)
                                        )
                                except BaseException:
                                    log.exception(
                                        "Error when normalizing BGP message: {}".format(
                                            norm_ris_msg
                                        )
                                    )
                    except Exception:
                        log.exception("exception message {}".format(data))
                log.warning("Iterator ran out of data; the connection will be retried")
            except Exception:
                log.info(
                    "RIPE RIS Server closed connection. Restarting socket in 60seconds.."
                )
                time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RIPE RIS Monitor")
    parser.add_argument(
        "-p",
        "--prefixes",
        type=str,
        dest="prefixes_file",
        default=None,
        help="Prefix(es) to be monitored (json file with prefix list)",
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
    hosts = args.hosts
    if hosts:
        hosts = set(hosts.split(","))
    ping_redis(redis)

    try:
        with Connection(RABBITMQ_URI) as connection:
            parse_ripe_ris(connection, args.prefixes_file, hosts)
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
