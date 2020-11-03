import time
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
from artemis_utils import signal_loading
from artemis_utils import translate_asn_range
from artemis_utils import translate_rfc2622
from artemis_utils.rest_util import ControlHandler
from artemis_utils.rest_util import HealthHandler
from artemis_utils.rest_util import setup_data_task
from artemis_utils.rest_util import start_data_task
from kombu import Connection
from kombu.mixins import ConsumerProducerMixin
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

log = get_logger()
MODULE_NAME = "prefixtree"
# TODO: add the following in utils
REST_PORT = 3000
CONFIGURATION_HOST = "configuration"


def configure_prefixtree(msg):
    signal_loading(MODULE_NAME, True)
    config = msg

    if config["timestamp"] > artemis_utils.rest_util.data_task.config_timestamp:
        artemis_utils.rest_util.data_task.monitors = msg.get("monitors", {})

        artemis_utils.rest_util.data_task.prefix_tree = {
            "v4": pytricia.PyTricia(32),
            "v6": pytricia.PyTricia(128),
        }
        rules = config.get("rules", [])
        try:
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
                        if artemis_utils.rest_util.data_task.prefix_tree[
                            ip_version
                        ].has_key(translated_prefix):
                            node = artemis_utils.rest_util.data_task.prefix_tree[
                                ip_version
                            ][translated_prefix]
                        else:
                            node = {"prefix": translated_prefix, "data": {"confs": []}}
                            artemis_utils.rest_util.data_task.prefix_tree[
                                ip_version
                            ].insert(translated_prefix, node)
                        node["data"]["confs"].append(conf_obj)

            # calculate the monitored and configured prefixes
            artemis_utils.rest_util.data_task.monitored_prefixes = set()
            artemis_utils.rest_util.data_task.configured_prefix_count = 0
            for ip_version in artemis_utils.rest_util.data_task.prefix_tree:
                for prefix in artemis_utils.rest_util.data_task.prefix_tree[ip_version]:
                    artemis_utils.rest_util.data_task.configured_prefix_count += 1
                    monitored_prefix = search_worst_prefix(
                        prefix,
                        artemis_utils.rest_util.data_task.prefix_tree[ip_version],
                    )
                    if monitored_prefix:
                        artemis_utils.rest_util.data_task.monitored_prefixes.add(
                            monitored_prefix
                        )

            signal_loading(MODULE_NAME, False)
            return {"success": True, "message": "configured"}
        except Exception:
            log.exception("{}".format(config))
            signal_loading(MODULE_NAME, False)
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
        self.write({"monitors": artemis_utils.rest_util.data_task.monitors})


class ConfiguredPrefixCountHandler(RequestHandler):
    """
    REST request handler for configured prefix count information.
    """

    def get(self):
        """
        Simply provides the configured prefix count (in the form of a JSON dict) to the requester
        """
        self.write(
            {
                "configured_prefix_count": artemis_utils.rest_util.data_task.configured_prefix_count
            }
        )


class MonitoredPrefixesHandler(RequestHandler):
    """
    REST request handler for  monitored prefixes information.
    """

    def get(self):
        """
        Simply provides the monitored prefixes (in the form of a JSON dict) to the requester
        """
        self.write(
            {
                "monitored_prefixes": list(
                    artemis_utils.rest_util.data_task.monitored_prefixes
                )
            }
        )


class PrefixTree:
    """
    Prefix Tree Service.
    """

    def __init__(self):
        self._running = False
        self.worker = None
        self.prefix_tree = None
        self.monitors = None
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
        self._running = True
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            log.info("stopped")
            self._running = False

    class Worker(ConsumerProducerMixin):
        """
        RabbitMQ Consumer/Producer for this Service.
        """

        def __init__(self, connection: Connection) -> NoReturn:
            self.connection = connection
            # TODO: exchanges and queues

        def get_consumers(self, Consumer, channel):
            return []


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

    # get initial configuration
    r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
    conf_res = configure_prefixtree(r.json())
    assert conf_res["success"], conf_res["message"]

    # prefixtree should start in any case
    start_data_task()
    while not artemis_utils.rest_util.data_task.is_running():
        time.sleep(1)

    # create REST worker
    app = make_app()
    app.listen(REST_PORT)
    log.info("Listening to port {}".format(REST_PORT))
    IOLoop.current().start()
