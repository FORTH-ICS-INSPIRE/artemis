import time
from threading import Lock
from typing import Dict
from typing import List
from typing import NoReturn

import artemis_utils.rest_util
import pytricia
import requests
import ujson as json
from artemis_utils import flatten
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import RABBITMQ_URI
from artemis_utils import search_worst_prefix
from artemis_utils import translate_asn_range
from artemis_utils import translate_rfc2622
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from artemis_utils.rest_util import ControlHandler
from artemis_utils.rest_util import HealthHandler
from artemis_utils.rest_util import setup_data_task
from artemis_utils.rest_util import start_data_task
from kombu import Connection
from kombu import Consumer
from kombu import serialization
from kombu.mixins import ConsumerProducerMixin
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

# logger
log = get_logger()

# tornado/service object locks
prefix_tree_lock = Lock()
monitors_lock = Lock()
stats_lock = Lock()

# additional serializer for pg-amqp messages
serialization.register(
    "txtjson", json.dumps, json.loads, content_type="text", content_encoding="utf-8"
)

# TODO: get the following from env
MODULE_NAME = "prefixtree"
CONFIGURATION_HOST = "configuration"
REST_PORT = 3000


def configure_prefixtree(msg):
    config = msg
    try:
        if config["timestamp"] > artemis_utils.rest_util.data_task.config_timestamp:
            monitors = msg.get("monitors", {})

            prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
            rules = config.get("rules", [])
            for rule in rules:
                rule_translated_origin_asn_set = set()
                for asn in rule["origin_asns"]:
                    this_translated_asn_list = flatten(translate_asn_range(asn))
                    rule_translated_origin_asn_set.update(set(this_translated_asn_list))
                rule["origin_asns"] = list(rule_translated_origin_asn_set)
                rule_translated_neighbor_set = set()
                for asn in rule["neighbors"]:
                    this_translated_asn_list = flatten(translate_asn_range(asn))
                    rule_translated_neighbor_set.update(set(this_translated_asn_list))
                rule["neighbors"] = list(rule_translated_neighbor_set)

                conf_obj = {
                    "origin_asns": rule["origin_asns"],
                    "neighbors": rule["neighbors"],
                    "prepend_seq": rule.get("prepend_seq", []),
                    "policies": set(rule["policies"]),
                    "community_annotations": rule["community_annotations"],
                }
                for prefix in rule["prefixes"]:
                    for translated_prefix in translate_rfc2622(prefix):
                        ip_version = get_ip_version(translated_prefix)
                        if prefix_tree[ip_version].has_key(translated_prefix):
                            node = prefix_tree[ip_version][translated_prefix]
                        else:
                            node = {
                                "prefix": translated_prefix,
                                "data": {"confs": []},
                                "timestamp": config["timestamp"],
                            }
                            prefix_tree[ip_version].insert(translated_prefix, node)
                        node["data"]["confs"].append(conf_obj)

            # calculate the monitored and configured prefixes
            configured_prefix_count = 0
            monitored_prefixes = set()
            for ip_version in prefix_tree:
                for prefix in prefix_tree[ip_version]:
                    configured_prefix_count += 1
                    monitored_prefix = search_worst_prefix(
                        prefix, prefix_tree[ip_version]
                    )
                    if monitored_prefix:
                        monitored_prefixes.add(monitored_prefix)

            prefix_tree_lock.acquire()
            artemis_utils.rest_util.data_task.prefix_tree = prefix_tree
            prefix_tree_lock.release()

            monitors_lock.acquire()
            artemis_utils.rest_util.data_task.monitors = monitors
            monitors_lock.release()

            stats_lock.acquire()
            artemis_utils.rest_util.data_task.monitored_prefixes = monitored_prefixes
            artemis_utils.rest_util.data_task.configured_prefix_count = (
                configured_prefix_count
            )
            stats_lock.release()
            artemis_utils.rest_util.data_task.config_timestamp = config["timestamp"]

            return {"success": True, "message": "configured"}
    except Exception:
        return {"success": False, "message": "error during data_task configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def post(self):
        """
        Cofnigures prefix tree and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        try:
            msg = json.loads(self.request.body)
            self.write(configure_prefixtree(msg))
        except Exception:
            self.write(
                {"success": False, "message": "error during data_task configuration"}
            )


class MonitorHandler(RequestHandler):
    """
    REST request handler for monitor information.
    """

    def get(self):
        """
        Simply provides the configured monitors (in the form of a JSON dict) to the requester
        """
        monitors_lock.acquire()
        self.write({"monitors": artemis_utils.rest_util.data_task.monitors})
        monitors_lock.release()


class ConfiguredPrefixCountHandler(RequestHandler):
    """
    REST request handler for configured prefix count information.
    """

    def get(self):
        """
        Simply provides the configured prefix count (in the form of a JSON dict) to the requester
        """
        stats_lock.acquire()
        self.write(
            {
                "configured_prefix_count": artemis_utils.rest_util.data_task.configured_prefix_count
            }
        )
        stats_lock.release()


class MonitoredPrefixesHandler(RequestHandler):
    """
    REST request handler for  monitored prefixes information.
    """

    def get(self):
        """
        Simply provides the monitored prefixes (in the form of a JSON dict) to the requester
        """
        stats_lock.acquire()
        self.write(
            {
                "monitored_prefixes": list(
                    artemis_utils.rest_util.data_task.monitored_prefixes
                )
            }
        )
        stats_lock.release()


class PrefixTree:
    """
    Prefix Tree Service.
    """

    def __init__(self):
        self._running = False
        self.worker = None
        self.prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
        self.monitors = {}
        self.monitored_prefixes = set()
        self.configured_prefix_count = 0
        self.config_timestamp = -1

    def is_running(self):
        return self._running

    def stop(self):
        if self.worker:
            self.worker.should_stop = True
        else:
            self._running = False

    def run(self) -> NoReturn:
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
                self._running = True
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            log.info("stopped")
            self._running = False

    def find_prefix_node(self, prefix):
        ip_version = get_ip_version(prefix)
        prefix_node = None
        # thread-safe access to prefix tree (can be changed by tornado config request handler)
        prefix_tree_lock.acquire()
        if prefix in self.prefix_tree[ip_version]:
            prefix_node = self.prefix_tree[ip_version][prefix]
        prefix_tree_lock.release()
        return prefix_node

    class Worker(ConsumerProducerMixin):
        """
        RabbitMQ Consumer/Producer for this Service.
        """

        def __init__(self, connection: Connection) -> NoReturn:
            self.connection = connection

            # EXCHANGES
            self.update_exchange = create_exchange(
                "bgp-update", connection, declare=True
            )
            self.hijack_exchange = create_exchange(
                "hijack-update", connection, declare=True
            )
            self.pg_amq_bridge = create_exchange("amq.direct", connection)

            # QUEUES
            self.update_queue = create_queue(
                MODULE_NAME,
                exchange=self.update_exchange,
                routing_key="update",
                priority=1,
            )
            self.hijack_ongoing_queue = create_queue(
                MODULE_NAME,
                exchange=self.hijack_exchange,
                routing_key="ongoing",
                priority=1,
            )
            self.pg_amq_update_queue = create_queue(
                MODULE_NAME,
                exchange=self.pg_amq_bridge,
                routing_key="update-insert",
                priority=1,
            )

        def get_consumers(
            self, Consumer: Consumer, channel: Connection
        ) -> List[Consumer]:
            return [
                Consumer(
                    queues=[self.update_queue],
                    on_message=self.annotate_bgp_update,
                    prefetch_count=100,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.hijack_ongoing_queue],
                    on_message=self.annotate_ongoing_hijack_updates,
                    prefetch_count=100,
                    accept=["ujson"],
                ),
                Consumer(
                    queues=[self.pg_amq_update_queue],
                    on_message=self.annotate_stored_bgp_update,
                    prefetch_count=100,
                    accept=["ujson", "txtjson"],
                ),
            ]

        def annotate_bgp_update(self, message: Dict) -> NoReturn:
            """
            Callback function that annotates an incoming bgp update with the associated
            configuration node (otherwise it discards it).
            """
            message.ack()
            bgp_update = message.payload
            try:
                prefix_node = artemis_utils.rest_util.data_task.find_prefix_node(
                    bgp_update["prefix"]
                )
                if prefix_node:
                    bgp_update["prefix_node"] = prefix_node
                    self.producer.publish(
                        bgp_update,
                        exchange=self.update_exchange,
                        routing_key="update-with-prefix-node",
                        serializer="ujson",
                    )
                else:
                    log.error(
                        "unconfigured BGP update received '{}'".format(bgp_update)
                    )
            except Exception:
                log.exception("exception")

        def annotate_stored_bgp_update(self, message: Dict) -> NoReturn:
            """
            Callback function that annotates an incoming (stored) bgp update with the associated
            configuration node (otherwise it discards it).
            """
            message.ack()
            bgp_update = message.payload
            try:
                prefix_node = artemis_utils.rest_util.data_task.find_prefix_node(
                    bgp_update["prefix"]
                )
                if prefix_node:
                    bgp_update["prefix_node"] = prefix_node
                    self.producer.publish(
                        bgp_update,
                        exchange=self.update_exchange,
                        routing_key="stored-update-with-prefix-node",
                        serializer="ujson",
                    )
                else:
                    log.error(
                        "unconfigured stored BGP update received '{}'".format(
                            bgp_update
                        )
                    )
            except Exception:
                log.exception("exception")

        def annotate_ongoing_hijack_updates(self, message: Dict) -> NoReturn:
            """
            Callback function that annotates incoming ongoing hijack updates with the associated
            configuration nodes (otherwise it discards them).
            """
            message.ack()
            bgp_updates = []
            for bgp_update in message.payload:
                try:
                    prefix_node = artemis_utils.rest_util.data_task.find_prefix_node(
                        bgp_update["prefix"]
                    )
                    if prefix_node:
                        bgp_update["prefix_node"] = prefix_node
                        bgp_updates.append(bgp_update)
                    else:
                        log.error(
                            "unconfigured stored BGP update received '{}'".format(
                                bgp_update
                            )
                        )
                except Exception:
                    log.exception("exception")
            self.producer.publish(
                bgp_updates,
                exchange=self.update_exchange,
                routing_key="ongoing-with-prefix-node",
                serializer="ujson",
            )


def make_app():
    return Application(
        [
            ("/config", ConfigHandler),
            ("/control", ControlHandler),
            ("/health", HealthHandler),
            ("/monitors", MonitorHandler),
            ("/configuredPrefixCount", ConfiguredPrefixCountHandler),
            ("/monitoredPrefixes", MonitoredPrefixesHandler),
        ]
    )


if __name__ == "__main__":
    # prefixtree should be initiated in any case
    setup_data_task(PrefixTree)

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_prefixtree(r.json())
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # prefixtree should start in any case
    start_data_task()
    while not artemis_utils.rest_util.data_task.is_running():
        time.sleep(1)

    # create REST worker
    app = make_app()
    app.listen(REST_PORT)
    log.info("Listening to port {}".format(REST_PORT))
    IOLoop.current().start()
