import argparse
import csv
import glob
import time

import ujson as json
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import uuid
from netaddr import IPAddress
from netaddr import IPNetwork
from utils import clean_as_path
from utils import get_logger
from utils import key_generator
from utils import load_json
from utils import mformat_validator
from utils import normalize_msg_path
from utils import RABBITMQ_URI

log = get_logger()


class BGPStreamHist:
    def __init__(self, prefixes_file=None, input_dir=None, autoconf=False):
        self.prefixes = load_json(prefixes_file)
        assert self.prefixes is not None
        self.input_dir = input_dir
        self.autoconf = autoconf
        self.autoconf_goahead = False

    def handle_autoconf_update_goahead_reply(self, message):
        message.ack()
        self.autoconf_goahead = True

    def parse_bgpstreamhist_csvs(self):
        # add /0 if autoconf
        if self.autoconf:
            self.prefixes.append("0.0.0.0/0")
            self.prefixes.append("::/0")

        with Connection(RABBITMQ_URI) as connection:
            self.update_exchange = Exchange(
                "bgp-update", channel=connection, type="direct", durable=False
            )
            self.update_exchange.declare()
            producer = Producer(connection)
            validator = mformat_validator()
            for csv_file in glob.glob("{}/*.csv".format(self.input_dir)):
                try:
                    with open(csv_file, "r") as f:
                        csv_reader = csv.reader(f, delimiter="|")
                        for row in csv_reader:
                            try:
                                if len(row) != 9:
                                    continue
                                if row[0].startswith("#"):
                                    continue
                                # example row: 139.91.0.0/16|8522|1403|1403 6461 2603 21320
                                # 5408
                                # 8522|routeviews|route-views2|A|"[{""asn"":1403,""value"":6461}]"|1517446677
                                this_prefix = row[0]
                                if row[6] == "A":
                                    as_path = row[3].split(" ")
                                    communities = json.loads(row[7])
                                else:
                                    as_path = []
                                    communities = []
                                service = "historical|{}|{}".format(row[4], row[5])
                                type_ = row[6]
                                timestamp = float(row[8])
                                peer_asn = int(row[2])
                                for prefix in self.prefixes:
                                    try:
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
                                            try:
                                                if validator.validate(msg):
                                                    msgs = normalize_msg_path(msg)
                                                    for msg in msgs:
                                                        key_generator(msg)
                                                        log.debug(msg)
                                                        if self.autoconf:
                                                            if str(our_prefix) in [
                                                                "0.0.0.0/0",
                                                                "::/0",
                                                            ]:
                                                                if msg["type"] == "A":
                                                                    as_path = clean_as_path(
                                                                        msg["path"]
                                                                    )
                                                                    if len(as_path) > 1:
                                                                        # ignore, since this is not a self-network origination, but sth transit
                                                                        break
                                                                elif msg["type"] == "W":
                                                                    # ignore irrelevant withdrawals
                                                                    break
                                                            self.autoconf_goahead = (
                                                                False
                                                            )
                                                            correlation_id = uuid()
                                                            callback_queue = Queue(
                                                                uuid(),
                                                                durable=False,
                                                                auto_delete=True,
                                                                max_priority=4,
                                                                consumer_arguments={
                                                                    "x-priority": 4
                                                                },
                                                            )
                                                            producer.publish(
                                                                msg,
                                                                exchange="",
                                                                routing_key="configuration.rpc.autoconf-update",
                                                                reply_to=callback_queue.name,
                                                                correlation_id=correlation_id,
                                                                retry=True,
                                                                declare=[
                                                                    Queue(
                                                                        "configuration.rpc.autoconf-update",
                                                                        durable=False,
                                                                        max_priority=4,
                                                                        consumer_arguments={
                                                                            "x-priority": 4
                                                                        },
                                                                    ),
                                                                    callback_queue,
                                                                ],
                                                                priority=4,
                                                                serializer="ujson",
                                                            )
                                                            with Consumer(
                                                                connection,
                                                                on_message=self.handle_autoconf_update_goahead_reply,
                                                                queues=[callback_queue],
                                                                accept=["ujson"],
                                                            ):
                                                                while (
                                                                    not self.autoconf_goahead
                                                                ):
                                                                    connection.drain_events()
                                                        producer.publish(
                                                            msg,
                                                            exchange=self.update_exchange,
                                                            routing_key="update",
                                                            serializer="ujson",
                                                        )
                                                        time.sleep(0.1)
                                                else:
                                                    log.warning(
                                                        "Invalid format message: {}".format(
                                                            msg
                                                        )
                                                    )
                                            except BaseException:
                                                log.exception(
                                                    "Error when normalizing BGP message: {}".format(
                                                        msg
                                                    )
                                                )
                                            break
                                    except Exception:
                                        log.exception("prefix")
                            except Exception:
                                log.exception("row")
                except Exception:
                    log.exception("exception")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGPStream Historical Monitor")
    parser.add_argument(
        "-p",
        "--prefixes",
        type=str,
        dest="prefixes_file",
        default=None,
        help="Prefix(es) to be monitored (json file with prefix list)",
    )
    parser.add_argument(
        "-d",
        "--dir",
        type=str,
        dest="dir",
        default=None,
        help="Directory with csvs to read",
    )
    parser.add_argument(
        "-a",
        "--autoconf",
        dest="autoconf",
        action="store_true",
        help="Use the feed from this historical route collector to build the configuration",
    )

    args = parser.parse_args()
    dir_ = args.dir.rstrip("/")
    log.info(
        "Starting BGPstreamhist on {} for {} (auto-conf: {})".format(
            dir_, args.prefixes_file, args.autoconf
        )
    )

    try:
        bgpstreamhist_instance = BGPStreamHist(args.prefixes_file, dir_, args.autoconf)
        bgpstreamhist_instance.parse_bgpstreamhist_csvs()
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
