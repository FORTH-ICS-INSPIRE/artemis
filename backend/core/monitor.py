import os
import re
import signal
from subprocess import Popen

import radix
import redis
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from utils import dump_json
from utils import exception_handler
from utils import flatten
from utils import get_logger
from utils import RABBITMQ_URI
from utils import REDIS_HOST
from utils import REDIS_PORT
from utils import translate_asn_range
from utils import translate_rfc2622

log = get_logger()
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60


class Monitor:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            if self.worker:
                self.worker.stop()
            log.info("stopped")

    def exit(self, signum, frame):
        if self.worker:
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):
        def __init__(self, connection):
            self.connection = connection
            self.timestamp = -1
            self.prefix_tree = None
            self.process_ids = []
            self.rules = None
            self.prefixes = set()
            self.prefix_file = "/root/monitor_prefixes.json"
            self.monitors = None
            self.flag = True
            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

            # EXCHANGES
            self.config_exchange = Exchange(
                "config", type="direct", durable=False, delivery_mode=1
            )

            # QUEUES
            self.config_queue = Queue(
                "monitor-config-notify",
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )

            self.config_request_rpc()

            # setup Redis monitor listeners
            self.setup_redis_mon_listeners()

            log.info("started")

        def setup_redis_mon_listeners(self):
            def redis_event_handler(msg):
                if "pattern" in msg and "channel" in msg and "data" in msg:
                    monitor_to_restart = None
                    for pubsub_mon_channel in self.redis_pubsub_mon_channels:
                        if (
                            str(msg["channel"].decode()) == pubsub_mon_channel
                            and str(msg["data"].decode()) == "expired"
                        ):
                            match_monitor = re.match(
                                r"^.*\:(.*)_seen_bgp_update$",
                                str(msg["channel"].decode()),
                            )
                            if match_monitor:
                                monitor_to_restart = match_monitor.group(1)
                                break
                if monitor_to_restart and self.flag:
                    try:
                        # first, check if this monitor is currently running
                        proc_id_to_terminate = None
                        for proc_id in self.process_ids:
                            name, pid = proc_id
                            if name.startswith("[{}]".format(monitor_to_restart)):
                                log.info(
                                    "{} needs restarting".format(monitor_to_restart)
                                )
                                # stop it
                                proc_id_to_terminate = proc_id
                                try:
                                    pid.terminate()
                                except ProcessLookupError:
                                    log.exception("process terminate")
                                break
                        # start it
                        if proc_id_to_terminate:
                            self.process_ids.remove(proc_id_to_terminate)
                            init_mon_instance = getattr(
                                self, "init_{}_instance".format(monitor_to_restart)
                            )
                            init_mon_instance()
                    except Exception:
                        log.exception("Exception")

            try:
                self.redis_pubsub = self.redis.pubsub()
                self.redis_pubsub_mon_channels = [
                    "__keyspace@0__:ris_seen_bgp_update",
                    "__keyspace@0__:betabmp_seen_bgp_update",
                    "__keyspace@0__:bgpstreamlive_seen_bgp_update",
                    "__keyspace@0__:exabgp_seen_bgp_update",
                ]
                for pubsub_mon_channel in self.redis_pubsub_mon_channels:
                    self.redis_pubsub.psubscribe(
                        **{pubsub_mon_channel: redis_event_handler}
                    )
                self.redis_listener_thread = self.redis_pubsub.run_in_thread(
                    sleep_time=1
                )
            except Exception:
                log.exception("Exception")

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    no_ack=True,
                )
            ]

        def handle_config_notify(self, message):
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            raw = message.payload
            if raw["timestamp"] > self.timestamp:
                self.timestamp = raw["timestamp"]
                self.rules = raw.get("rules", [])
                self.monitors = raw.get("monitors", {})
                self.start_monitors()

        def start_monitors(self):
            for proc_id in self.process_ids:
                try:
                    proc_id[1].terminate()
                except ProcessLookupError:
                    log.exception("process terminate")
            self.process_ids.clear()
            self.prefixes.clear()

            self.prefix_tree = radix.Radix()
            for rule in self.rules:
                try:
                    rule_translated_prefix_set = set()
                    for prefix in rule["prefixes"]:
                        this_translated_prefix_list = flatten(translate_rfc2622(prefix))
                        rule_translated_prefix_set.update(
                            set(this_translated_prefix_list)
                        )
                    rule["prefixes"] = list(rule_translated_prefix_set)
                    for prefix in rule["prefixes"]:
                        node = self.prefix_tree.add(prefix)

                        rule_translated_origin_asn_set = set()
                        for asn in rule["origin_asns"]:
                            this_translated_asn_list = flatten(translate_asn_range(asn))
                            rule_translated_origin_asn_set.update(
                                set(this_translated_asn_list)
                            )
                        rule["origin_asns"] = list(rule_translated_origin_asn_set)
                        rule_translated_neighbor_set = set()
                        for asn in rule["neighbors"]:
                            this_translated_asn_list = flatten(translate_asn_range(asn))
                            rule_translated_neighbor_set.update(
                                set(this_translated_asn_list)
                            )
                        rule["neighbors"] = list(rule_translated_neighbor_set)

                        node.data["origin_asns"] = rule["origin_asns"]
                        node.data["neighbors"] = rule["neighbors"]
                        node.data["mitigation"] = rule["mitigation"]
                except Exception:
                    log.exception("Exception")

            # only keep super prefixes for monitors
            for prefix in self.prefix_tree.prefixes():
                self.prefixes.add(self.prefix_tree.search_worst(prefix).prefix)
            dump_json(list(self.prefixes), self.prefix_file)

            self.init_ris_instance()
            self.init_exabgp_instance()
            self.init_bgpstreamhist_instance()
            self.init_bgpstreamlive_instance()
            self.init_betabmp_instance()

        def stop(self):
            if self.flag:
                for proc_id in self.process_ids:
                    try:
                        proc_id[1].terminate()
                    except ProcessLookupError:
                        log.exception("process terminate")
                self.flag = False
                self.rules = None
                self.monitors = None
                if os.path.isfile(self.prefix_file):
                    os.remove(self.prefix_file)

        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            self.producer.publish(
                "",
                exchange="",
                routing_key="config-request-queue",
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
                retry=True,
                declare=[
                    Queue(
                        "config-request-queue",
                        durable=False,
                        max_priority=4,
                        consumer_arguments={"x-priority": 4},
                    ),
                    callback_queue,
                ],
                priority=4,
            )
            with Consumer(
                self.connection,
                on_message=self.handle_config_request_reply,
                queues=[callback_queue],
                no_ack=True,
            ):
                while not self.rules and not self.monitors:
                    self.connection.drain_events()

        def handle_config_request_reply(self, message):
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.monitors = raw.get("monitors", {})
                    self.start_monitors()

        @exception_handler(log)
        def init_ris_instance(self):
            if "riperis" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["riperis"], self.prefix_file
                    )
                )
                rrcs = ",".join(self.monitors["riperis"])
                p = Popen(
                    [
                        "/usr/local/bin/python3",
                        "taps/ripe_ris.py",
                        "--prefixes",
                        self.prefix_file,
                        "--hosts",
                        rrcs,
                    ],
                    shell=False,
                )
                self.process_ids.append(
                    ("[ris] {} {}".format(rrcs, self.prefix_file), p)
                )
                self.redis.set(
                    "ris_seen_bgp_update",
                    "1",
                    ex=int(
                        os.getenv(
                            "MON_TIMEOUT_LAST_BGP_UPDATE",
                            DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                        )
                    ),
                )

        @exception_handler(log)
        def init_exabgp_instance(self):
            if "exabgp" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["exabgp"], self.prefix_file
                    )
                )
                for exabgp_monitor in self.monitors["exabgp"]:
                    exabgp_monitor_str = "{}:{}".format(
                        exabgp_monitor["ip"], exabgp_monitor["port"]
                    )
                    p = Popen(
                        [
                            "/usr/local/bin/python3",
                            "taps/exabgp_client.py",
                            "--prefixes",
                            self.prefix_file,
                            "--host",
                            exabgp_monitor_str,
                        ],
                        shell=False,
                    )
                    self.process_ids.append(
                        (
                            "[exabgp] {} {}".format(
                                exabgp_monitor_str, self.prefix_file
                            ),
                            p,
                        )
                    )
                    self.redis.set(
                        "exabgp_seen_bgp_update",
                        "1",
                        ex=os.getenv(
                            "MON_TIMEOUT_LAST_BGP_UPDATE",
                            DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                        ),
                    )

        @exception_handler(log)
        def init_bgpstreamhist_instance(self):
            if "bgpstreamhist" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["bgpstreamhist"], self.prefix_file
                    )
                )
                bgpstreamhist_dir = self.monitors["bgpstreamhist"]
                p = Popen(
                    [
                        "/usr/local/bin/python3",
                        "taps/bgpstreamhist.py",
                        "--prefixes",
                        self.prefix_file,
                        "--dir",
                        bgpstreamhist_dir,
                    ],
                    shell=False,
                )
                self.process_ids.append(
                    (
                        "[bgpstreamhist] {} {}".format(
                            bgpstreamhist_dir, self.prefix_file
                        ),
                        p,
                    )
                )

        @exception_handler(log)
        def init_bgpstreamlive_instance(self):
            if "bgpstreamlive" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["bgpstreamlive"], self.prefix_file
                    )
                )
                bgpstream_projects = ",".join(self.monitors["bgpstreamlive"])
                p = Popen(
                    [
                        "/usr/local/bin/python3",
                        "taps/bgpstreamlive.py",
                        "--prefixes",
                        self.prefix_file,
                        "--mon_projects",
                        bgpstream_projects,
                    ],
                    shell=False,
                )
                self.process_ids.append(
                    (
                        "[bgpstreamlive] {} {}".format(
                            bgpstream_projects, self.prefix_file
                        ),
                        p,
                    )
                )
                self.redis.set(
                    "bgpstreamlive_seen_bgp_update",
                    "1",
                    ex=os.getenv(
                        "MON_TIMEOUT_LAST_BGP_UPDATE",
                        DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                    ),
                )

        @exception_handler(log)
        def init_betabmp_instance(self):
            if "betabmp" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["betabmp"], self.prefix_file
                    )
                )
                p = Popen(
                    [
                        "/usr/local/bin/python3",
                        "taps/betabmp.py",
                        "--prefixes",
                        self.prefix_file,
                    ],
                    shell=False,
                )
                self.process_ids.append(("[betabmp] {}".format(self.prefix_file), p))
                self.redis.set(
                    "betabmp_seen_bgp_update",
                    "1",
                    ex=os.getenv(
                        "MON_TIMEOUT_LAST_BGP_UPDATE",
                        DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                    ),
                )


def run():
    service = Monitor()
    service.run()


if __name__ == "__main__":
    run()
