import argparse
import os

import _pybgpstream
import redis
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from netaddr import IPAddress
from netaddr import IPNetwork
from utils import get_logger
from utils import key_generator
from utils import load_json
from utils import mformat_validator
from utils import normalize_msg_path
from utils import RABBITMQ_URI

# install as described in https://bgpstream.caida.org/docs/install/pybgpstream

log = get_logger()
redis_host = os.getenv("REDIS_HOST", "backend")
redis_port = os.getenv("REDIS_PORT", 6739)
redis = redis.Redis(host=redis_host, port=redis_port)


def run_bgpstream_beta_bmp(prefixes_file=None):
    """
    Retrieve all elements related to a list of prefixes
    https://bgpstream.caida.org/docs/api/pybgpstream/_pybgpstream.html

    :param prefixes_file: <str> input prefix json

    :return: -
    """

    prefixes = load_json(prefixes_file)
    assert prefixes is not None

    # create a new bgpstream instance
    stream = _pybgpstream.BGPStream()

    # set BMP data interface
    stream.set_data_interface("beta-bmp-stream")

    # filter prefixes
    for prefix in prefixes:
        stream.add_filter("prefix", prefix)

    # filter record type
    stream.add_filter("record-type", "updates")

    # set live mode
    stream.set_live_mode()

    # start the stream
    stream.start()

    with Connection(RABBITMQ_URI) as connection:
        exchange = Exchange(
            "bgp-update", channel=connection, type="direct", durable=False
        )
        exchange.declare()
        producer = Producer(connection)
        validator = mformat_validator()
        while True:
            # get next record
            try:
                rec = stream.get_next_record()
            except BaseException:
                continue
            if (rec.status != "valid") or (rec.type != "update"):
                continue

            # get next element
            try:
                elem = rec.get_next_elem()
            except BaseException:
                continue

            while elem:
                if elem.type in {"A", "W"}:
                    redis.set("betabmp_seen_bgp_update", "1", ex=60 * 60)
                    this_prefix = str(elem.fields["prefix"])
                    service = "betabmp|{}|{}".format(
                        str(rec.project), str(rec.collector)
                    )
                    type_ = elem.type
                    if type_ == "A":
                        as_path = elem.fields["as-path"].split(" ")
                        communities = [
                            {
                                "asn": int(comm.split(":")[0]),
                                "value": int(comm.split(":")[1]),
                            }
                            for comm in elem.fields["communities"]
                        ]
                    else:
                        as_path = []
                        communities = []
                    timestamp = float(rec.time)
                    peer_asn = elem.peer_asn

                    for prefix in prefixes:
                        base_ip, mask_length = this_prefix.split("/")
                        our_prefix = IPNetwork(prefix)
                        if (
                            IPAddress(base_ip) in our_prefix
                            and int(mask_length) >= our_prefix.prefixlen
                        ):
                            msg = {
                                "type": type_,
                                "timestamp": timestamp,
                                "path": as_path,
                                "service": service,
                                "communities": communities,
                                "prefix": this_prefix,
                                "peer_asn": peer_asn,
                            }
                            if validator.validate(msg):
                                msgs = normalize_msg_path(msg)
                                for msg in msgs:
                                    key_generator(msg)
                                    log.debug(msg)
                                    producer.publish(
                                        msg,
                                        exchange=exchange,
                                        routing_key="update",
                                        serializer="json",
                                    )
                            else:
                                log.warning("Invalid format message: {}".format(msg))
                try:
                    elem = rec.get_next_elem()
                except BaseException:
                    continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Beta BMP Live Monitor")
    parser.add_argument(
        "-p",
        "--prefixes",
        type=str,
        dest="prefixes_file",
        default=None,
        help="Prefix(es) to be monitored (json file with prefix list)",
    )

    args = parser.parse_args()

    try:
        run_bgpstream_beta_bmp(args.prefixes_file)
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
