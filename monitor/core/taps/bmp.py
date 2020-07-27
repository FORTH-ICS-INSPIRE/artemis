import argparse
import os
import sys

import pytricia
import redis
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import uuid
from utils import clean_as_path
from utils import get_ip_version
from utils import get_logger
from utils import key_generator
from utils import load_json
from utils import mformat_validator
from utils import normalize_msg_path
from utils import ping_redis
from utils import RABBITMQ_URI
from utils import REDIS_HOST
from utils import REDIS_PORT
from yabgp.common import constants as bgp_cons
from yabmp import service
from yabmp.handler import BaseHandler

log = get_logger()
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60


class ArtemisHandler(BaseHandler):
    """Custom Artemis Handler to send BGP Update messages to a RabbitMQ exchange
    """

    def __init__(
        self, connection, prefixes_file="/root/monitor_prefixes.json", autoconf=False
    ):
        super(ArtemisHandler, self).__init__()
        # RabbitMQ
        self.connection = connection
        self.update_exchange = Exchange(
            "bgp-update", channel=connection, type="direct", durable=False
        )
        self.update_exchange.declare()

        # Prefixes
        self.prefixes = load_json(prefixes_file)
        assert self.prefixes is not None
        self.prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}

        # Autoconfiguration
        self.autoconf = autoconf
        self.autoconf_goahead = False
        # add /0 if autoconf
        if self.autoconf:
            self.prefixes.append("0.0.0.0/0")
            self.prefixes.append("::/0")

        # Prefix-tree calculation
        for prefix in self.prefixes:
            ip_version = get_ip_version(prefix)
            self.prefix_tree[ip_version].insert(prefix, "")

        # Validator
        self.validator = mformat_validator()

    def init(self):
        """init
        """
        pass

    def on_connection_made(self, peer_host, peer_port):
        """process for connection made
        """
        pass

    def on_connection_lost(self, peer_host, peer_port):
        """process for connection lost
        """
        pass

    def on_message_received(self, peer_host, peer_port, recv_msg, msg_type):
        """process for message received
        """
        if msg_type in [4, 5, 6]:
            return
        peer_asn = recv_msg[0]["as"]
        timestamp = recv_msg[0]["time"][0]

        if msg_type == 0:  # route monitoring message
            redis.set(
                "bmp_seen_bgp_update",
                "1",
                ex=int(
                    os.getenv(
                        "MON_TIMEOUT_LAST_BGP_UPDATE",
                        DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                    )
                ),
            )

            withdraw = recv_msg[1][1]["withdraw"]
            msg_type = "A" if withdraw == [] else "W"
            prefixes = recv_msg[1][1]["nlri"]
            attr = recv_msg[1][1]["attr"]
            path = [
                val
                for t, val in attr.get(bgp_cons.BGPTYPE_AS_PATH, [])
                if t == bgp_cons.AS_SEQUENCE
            ]
            communities = [
                {"asn": int(comm.split(":")[0]), "value": int(comm.split(":")[1])}
                for comm in attr.get(bgp_cons.BGPTYPE_COMMUNITIES, [])
            ]
            messages = []
            if msg_type == "A":
                for prefix in prefixes:
                    ip_version = get_ip_version(prefix)
                    try:
                        if prefix in self.prefix_tree[ip_version]:
                            msg = {
                                "service": "BMP|{}".format(peer_host),
                                "type": msg_type,
                                "prefix": prefix,
                                "path": path,
                                "communities": communities,
                                "timestamp": timestamp,
                                "peer_asn": peer_asn,
                            }
                            messages += normalize_msg_path(msg)
                    except RuntimeError:
                        log.exception("exception")
            elif msg_type == "W":
                for prefix in withdraw:
                    ip_version = get_ip_version(prefix)
                    try:
                        if prefix in self.prefix_tree[ip_version]:
                            msg = {
                                "service": "BMP|",
                                "type": msg_type,
                                "prefix": prefix,
                                "path": [],
                                "communities": [],
                                "timestamp": timestamp,
                                "peer_asn": peer_asn,
                            }
                            messages += normalize_msg_path(msg)
                    except RuntimeError:
                        log.exception("exception")
            for msg in messages:
                try:
                    if mformat_validator.validate(msg):
                        key_generator(msg)
                        log.debug(msg)
                        with Producer(self.connection) as producer:
                            if self.autoconf:
                                if msg["type"] == "A":
                                    as_path = clean_as_path(msg["path"])
                                    if len(as_path) > 1:
                                        # ignore, since this is not a self-network origination, but sth transit
                                        break
                                elif msg["type"] == "W":
                                    # ignore irrelevant withdrawals
                                    break
                                self.autoconf_goahead = False
                                correlation_id = uuid()
                                callback_queue = Queue(
                                    uuid(),
                                    durable=False,
                                    auto_delete=True,
                                    max_priority=4,
                                    consumer_arguments={"x-priority": 4},
                                )
                                producer.publish(
                                    msg,
                                    exchange="",
                                    routing_key="conf-autoconf-update-queue",
                                    reply_to=callback_queue.name,
                                    correlation_id=correlation_id,
                                    retry=True,
                                    declare=[
                                        Queue(
                                            "conf-autoconf-update-queue",
                                            durable=False,
                                            max_priority=4,
                                            consumer_arguments={"x-priority": 4},
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
                                    while not self.autoconf_goahead:
                                        connection.drain_events()
                            producer.publish(
                                msg,
                                exchange=self.update_exchange,
                                routing_key="update",
                                serializer="ujson",
                            )
                    else:
                        log.warning("Invalid format message: {}".format(msg))
                except BaseException:
                    log.exception("Error when normalizing BGP message: {}".format(msg))

    def handle_autoconf_update_goahead_reply(self, message):
        message.ack()
        self.autoconf_goahead = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BMP Server")
    parser.add_argument(
        "-p",
        "--prefixes",
        type=str,
        dest="prefixes_file",
        default=None,
        help="Prefix(es) to be monitored (json file with prefix list)",
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

    log.info("Starting BMP")
    try:
        with Connection(RABBITMQ_URI) as connection:
            handler = ArtemisHandler(connection)
            sys.argv = [sys.argv[0]]  # remove args for bmp
            service.prepare_service(handler=handler)
    except RuntimeError:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
