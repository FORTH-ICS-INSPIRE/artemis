import argparse
import signal

from kombu import Connection
from kombu import Exchange
from kombu import Producer
from socketIO_client import BaseNamespace
from socketIO_client import SocketIO
from utils import get_logger
from utils import key_generator
from utils import load_json
from utils import mformat_validator
from utils import normalize_msg_path
from utils import RABBITMQ_URI

log = get_logger()


class ExaBGP:
    def __init__(self, prefixes_file, host):
        self.host = host
        self.prefixes = load_json(prefixes_file)
        assert self.prefixes is not None
        self.sio = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def start(self):
        with Connection(RABBITMQ_URI) as connection:
            self.connection = connection
            self.exchange = Exchange(
                "bgp-update", channel=connection, type="direct", durable=False
            )
            self.exchange.declare()

            try:
                self.sio = SocketIO("http://" + self.host, namespace=BaseNamespace)

                def exabgp_msg(bgp_message):
                    msg = {
                        "type": bgp_message["type"],
                        "communities": bgp_message.get("communities", []),
                        "timestamp": float(bgp_message["timestamp"]),
                        "path": bgp_message.get("path", []),
                        "service": "exabgp|{}".format(self.host),
                        "prefix": bgp_message["prefix"],
                        "peer_asn": int(bgp_message["peer_asn"]),
                    }
                    if mformat_validator(msg):
                        with Producer(connection) as producer:
                            msgs = normalize_msg_path(msg)
                            for msg in msgs:
                                key_generator(msg)
                                log.debug(msg)
                                producer.publish(
                                    msg,
                                    exchange=self.exchange,
                                    routing_key="update",
                                    serializer="json",
                                )
                    else:
                        log.warning("Invalid format message: {}".format(msg))

                self.sio.on("exa_message", exabgp_msg)
                self.sio.emit("exa_subscribe", {"prefixes": self.prefixes})
                self.sio.wait()
            except KeyboardInterrupt:
                self.exit()
            except Exception:
                log.exception("exception")

    def exit(self):
        print("Exiting ExaBGP")
        if self.sio is not None:
            self.sio.disconnect()
            self.sio.wait()


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

    args = parser.parse_args()

    print("Starting ExaBGP on {} for {}".format(args.host, args.prefixes_file))
    try:
        exa = ExaBGP(args.prefixes_file, args.host)
        exa.start()
    except BaseException:
        log.exception("exception")
