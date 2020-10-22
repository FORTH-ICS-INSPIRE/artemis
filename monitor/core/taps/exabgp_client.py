import argparse
import os
import signal
import socket
from threading import Timer

import redis
from artemis_utils import get_logger
from artemis_utils import key_generator
from artemis_utils import load_json
from artemis_utils import mformat_validator
from artemis_utils import normalize_msg_path
from artemis_utils import ping_redis
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import REDIS_PORT
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Consumer
from kombu import Producer
from netaddr import IPAddress
from netaddr import IPNetwork
from socketIO_client import BaseNamespace
from socketIO_client import SocketIO

log = get_logger()
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60
AUTOCONF_INTERVAL = 1
MAX_AUTOCONF_UPDATES = 20
MAX_AUTOCONF_NOTIFY_TIMEOUT = 60


class ExaBGP:
    def __init__(self, prefixes_file, host, autoconf=False):
        self.module_name = "exabgp|{}".format(host)
        self.host = host
        # use /0 if autoconf
        if autoconf:
            self.prefixes = ["0.0.0.0/0", "::/0"]
        else:
            self.prefixes = load_json(prefixes_file)
        assert self.prefixes is not None
        self.sio = None
        self.connection = None
        self.update_exchange = None
        self.config_exchange = None
        self.config_queue = None
        self.autoconf = autoconf
        self.autoconf_goahead = False
        self.autoconf_timer_thread = None
        self.autoconf_updates = []
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

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
        try:
            if len(self.autoconf_updates) == 0:
                return
            autoconf_updates_to_send = self.autoconf_updates[:MAX_AUTOCONF_UPDATES]
            log.info(
                "About to send {} autoconf updates".format(
                    len(autoconf_updates_to_send)
                )
            )
            self.autoconf_goahead = False
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
            with Consumer(
                self.connection,
                on_message=self.handle_autoconf_update_goahead_reply,
                queues=[self.config_queue],
                accept=["ujson"],
            ):
                while not self.autoconf_goahead:
                    try:
                        self.connection.drain_events(
                            timeout=MAX_AUTOCONF_NOTIFY_TIMEOUT
                        )
                    except socket.timeout:
                        log.error("autoconf timeout")
                        break
        except Exception:
            log.exception("exception")
        finally:
            self.setup_autoconf_update_timer()

    def handle_autoconf_update_goahead_reply(self, message):
        message.ack()
        self.autoconf_goahead = True

    def start(self):
        with Connection(RABBITMQ_URI) as connection:
            self.connection = connection
            self.update_exchange = create_exchange(
                "bgp-update", connection, declare=True
            )
            self.config_exchange = create_exchange("config", connection, declare=True)
            self.config_queue = create_queue(
                self.module_name,
                exchange=self.config_exchange,
                routing_key="notify",
                priority=3,
                random=True,
            )

            if self.autoconf:
                if self.autoconf_timer_thread is not None:
                    self.autoconf_timer_thread.cancel()
                self.setup_autoconf_update_timer()

            validator = mformat_validator()

            try:
                self.sio = SocketIO("http://" + self.host, namespace=BaseNamespace)

                def exabgp_msg(bgp_message):
                    redis.set(
                        "exabgp_seen_bgp_update",
                        "1",
                        ex=int(
                            os.getenv(
                                "MON_TIMEOUT_LAST_BGP_UPDATE",
                                DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                            )
                        ),
                    )
                    msg = {
                        "type": bgp_message["type"],
                        "communities": bgp_message.get("communities", []),
                        "timestamp": float(bgp_message["timestamp"]),
                        "path": bgp_message.get("path", []),
                        "service": "exabgp|{}".format(self.host),
                        "prefix": bgp_message["prefix"],
                        "peer_asn": int(bgp_message["peer_asn"]),
                    }
                    for prefix in self.prefixes:
                        try:
                            base_ip, mask_length = bgp_message["prefix"].split("/")
                            our_prefix = IPNetwork(prefix)
                            if (
                                IPAddress(base_ip) in our_prefix
                                and int(mask_length) >= our_prefix.prefixlen
                            ):
                                try:
                                    if validator.validate(msg):
                                        msgs = normalize_msg_path(msg)
                                        for msg in msgs:
                                            key_generator(msg)
                                            log.debug(msg)
                                            if self.autoconf:
                                                self.autoconf_updates.append(msg)
                                            else:
                                                with Producer(connection) as producer:
                                                    producer.publish(
                                                        msg,
                                                        exchange=self.update_exchange,
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
                                            msg
                                        )
                                    )
                                break
                        except Exception:
                            log.exception("exception")

                self.sio.on("exa_message", exabgp_msg)
                self.sio.emit("exa_subscribe", {"prefixes": self.prefixes})
                self.sio.wait()
            except KeyboardInterrupt:
                self.exit()
            except Exception:
                log.exception("exception")

    def exit(self, signum, frame):
        log.info("Exiting ExaBGP")
        if self.sio is not None:
            self.sio.disconnect()
        log.info("ExaBGP exited")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ExaBGP Monitor Client")
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
        "--host",
        type=str,
        dest="host",
        default=None,
        help="Prefix to be monitored",
    )
    parser.add_argument(
        "-a",
        "--autoconf",
        dest="autoconf",
        action="store_true",
        help="Use the feed from this local route collector to build the configuration",
    )

    args = parser.parse_args()
    ping_redis(redis)

    log.info(
        "Starting ExaBGP on {} for {} (auto-conf: {})".format(
            args.host, args.prefixes_file, args.autoconf
        )
    )
    try:
        exa = ExaBGP(args.prefixes_file, args.host, args.autoconf)
        exa.start()
    except BaseException:
        log.exception("exception")
