import argparse
import csv
import glob
import time
from threading import Timer

import ujson as json
from artemis_utils import get_logger
from artemis_utils import key_generator
from artemis_utils import load_json
from artemis_utils import mformat_validator
from artemis_utils import normalize_msg_path
from artemis_utils import RABBITMQ_URI
from artemis_utils.rabbitmq_util import create_exchange
from kombu import Connection
from kombu import Producer
from netaddr import IPAddress
from netaddr import IPNetwork

log = get_logger()
AUTOCONF_INTERVAL = 1
MAX_AUTOCONF_UPDATES = 100


class BGPStreamHist:
    def __init__(self, prefixes_file=None, input_dir=None, autoconf=False):
        self.module_name = "bgpstreamhist|{}".format(input_dir)
        # use /0 if autoconf
        if autoconf:
            self.prefixes = ["0.0.0.0/0", "::/0"]
        else:
            self.prefixes = load_json(prefixes_file)
        assert self.prefixes is not None
        self.input_dir = input_dir
        self.connection = None
        self.update_exchange = None
        self.config_exchange = None
        self.config_queue = None
        self.autoconf = autoconf
        self.autoconf_timer_thread = None
        self.autoconf_updates = []

    def setup_autoconf_update_timer(self):
        """
        Timer for autoconf update message send. Periodically (every 1 second),
        it sends buffered autoconf messages to configuration for processing
        :return:
        """
        self.autoconf_timer_thread = Timer(
            interval=1, function=self.send_autoconf_updates
        )
        self.autoconf_timer_thread.start()

    def send_autoconf_updates(self):
        if len(self.autoconf_updates) == 0:
            self.setup_autoconf_update_timer()
            return
        try:
            autoconf_updates_to_send = self.autoconf_updates[:MAX_AUTOCONF_UPDATES]
            log.info(
                "About to send {} autoconf updates".format(
                    len(autoconf_updates_to_send)
                )
            )
            if self.connection is None:
                self.connection = Connection(RABBITMQ_URI)
            with Producer(self.connection) as producer:
                producer.publish(
                    autoconf_updates_to_send,
                    exchange=self.config_exchange,
                    routing_key="autoconf-update",
                    retry=True,
                    priority=4,
                    serializer="ujson",
                )
            for i in range(len(autoconf_updates_to_send)):
                del self.autoconf_updates[0]
            log.info("{} autoconf updates remain".format(len(self.autoconf_updates)))
            if self.connection is None:
                self.connection = Connection(RABBITMQ_URI)
        except Exception:
            log.exception("exception")
        finally:
            self.setup_autoconf_update_timer()

    def parse_bgpstreamhist_csvs(self):
        with Connection(RABBITMQ_URI) as connection:
            self.update_exchange = create_exchange(
                "bgp-update", connection, declare=True
            )
            self.config_exchange = create_exchange("config", connection, declare=True)
            producer = Producer(connection)

            if self.autoconf:
                if self.autoconf_timer_thread is not None:
                    self.autoconf_timer_thread.cancel()
                self.setup_autoconf_update_timer()

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
                                                            self.autoconf_updates.append(
                                                                msg
                                                            )
                                                        else:
                                                            producer.publish(
                                                                msg,
                                                                exchange=self.update_exchange,
                                                                routing_key="update",
                                                                serializer="ujson",
                                                            )
                                                            time.sleep(0.01)
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
