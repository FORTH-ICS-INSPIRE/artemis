import logging
import multiprocessing as mp
import os
from typing import Dict
from typing import List
from typing import NoReturn

import pytricia
import requests
import ujson as json
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import hijack_log_field_formatter
from artemis_utils import RABBITMQ_URI
from artemis_utils import translate_rfc2622
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Consumer
from kombu import Producer
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

# loggers
log = get_logger()
hij_log = logging.getLogger("hijack_logger")
mail_log = logging.getLogger("mail_logger")
try:
    hij_log_filter = json.loads(os.getenv("HIJACK_LOG_FILTER", "[]"))
except Exception:
    log.exception("exception")
    hij_log_filter = []


# log filter for hijack alerts
class HijackLogFilter(logging.Filter):
    def filter(self, rec):
        if not hij_log_filter:
            return True
        for filter_entry in hij_log_filter:
            for filter_entry_key in filter_entry:
                if rec.__dict__[filter_entry_key] == filter_entry[filter_entry_key]:
                    return True
        return False


# apply log filter
mail_log.addFilter(HijackLogFilter())
hij_log.addFilter(HijackLogFilter())

# shared memory object locks
shared_memory_locks = {
    "data_worker": mp.Lock(),
    "autoignore": mp.Lock(),
    "config_timestamp": mp.Lock(),
}

# global vars
MODULE_NAME = os.getenv("MODULE_NAME", "prefixtree")
CONFIGURATION_HOST = os.getenv("CONFIGURATION_HOST", "configuration")
REST_PORT = int(os.getenv("REST_PORT", 3000))


# TODO: move this to artemis-utils
def pytricia_to_dict(pyt_tree):
    pyt_dict = {}
    for prefix in pyt_tree:
        pyt_dict[prefix] = pyt_tree[prefix]
    return pyt_dict


# TODO: move this to artemis-utils
def dict_to_pytricia(dict_tree, size=32):
    pyt_tree = pytricia.PyTricia(size)
    for prefix in dict_tree:
        pyt_tree.insert(prefix, dict_tree[prefix])
    return pyt_tree


def configure_notifier(msg, shared_memory_manager_dict):
    config = msg
    try:
        # check newer config
        shared_memory_locks["config_timestamp"].acquire()
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        shared_memory_locks["config_timestamp"].release()
        if config["timestamp"] > config_timestamp:

            # extract autoignore rules
            autoignore_rules = config.get("autoignore", {})

            # calculate autoignore prefix tree
            autoignore_prefix_tree = {
                "v4": pytricia.PyTricia(32),
                "v6": pytricia.PyTricia(128),
            }
            for key in autoignore_rules:
                rule = autoignore_rules[key]
                for prefix in rule["prefixes"]:
                    for translated_prefix in translate_rfc2622(prefix):
                        ip_version = get_ip_version(translated_prefix)
                        if not autoignore_prefix_tree[ip_version].has_key(
                            translated_prefix
                        ):
                            node = {"prefix": translated_prefix, "rule_key": key}
                            autoignore_prefix_tree[ip_version].insert(
                                translated_prefix, node
                            )

            # note that the object should be picklable (e.g., dict instead of pytricia tree,
            # see also: https://github.com/jsommers/pytricia/issues/20)
            dict_autoignore_prefix_tree = {
                "v4": pytricia_to_dict(autoignore_prefix_tree["v4"]),
                "v6": pytricia_to_dict(autoignore_prefix_tree["v6"]),
            }
            shared_memory_locks["autoignore"].acquire()
            shared_memory_manager_dict["autoignore_rules"] = autoignore_rules
            shared_memory_manager_dict[
                "autoignore_prefix_tree"
            ] = dict_autoignore_prefix_tree
            shared_memory_manager_dict["autoignore_recalculate"] = True
            shared_memory_locks["autoignore"].release()

            shared_memory_locks["config_timestamp"].acquire()
            shared_memory_manager_dict["config_timestamp"] = config_timestamp
            shared_memory_locks["config_timestamp"].release()

            return {"success": True, "message": "configured"}
    except Exception:
        log.exception("exception")
        return {"success": False, "message": "error during data_task configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def post(self):
        """
        Configures prefix tree and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        try:
            msg = json.loads(self.request.body)
            self.write(configure_notifier(msg, self.shared_memory_manager_dict))
        except Exception:
            self.write(
                {"success": False, "message": "error during data_task configuration"}
            )


class HealthHandler(RequestHandler):
    """
    REST request handler for health checks.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Extract the status of a service via a GET request.
        :return: {"status" : <unconfigured|running|stopped>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
        shared_memory_locks["data_worker"].release()
        self.write({"status": status})


class ControlHandler(RequestHandler):
    """
    REST request handler for control commands.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def start_data_worker(self):
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            log.info("data worker already running")
            shared_memory_locks["data_worker"].release()
            return "already running"
        shared_memory_locks["data_worker"].release()
        mp.Process(target=self.run_data_worker_process).start()
        return "instructed to start"

    def run_data_worker_process(self):
        try:
            with Connection(RABBITMQ_URI) as connection:
                shared_memory_locks["data_worker"].acquire()
                data_worker = NotifierDataWorker(
                    connection, self.shared_memory_manager_dict
                )
                self.shared_memory_manager_dict["data_worker_running"] = True
                shared_memory_locks["data_worker"].release()
                log.info("data worker started")
                data_worker.run()
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["data_worker"].acquire()
            self.shared_memory_manager_dict["data_worker_running"] = False
            shared_memory_locks["data_worker"].release()
            log.info("data worker stopped")

    @staticmethod
    def stop_data_worker():
        shared_memory_locks["data_worker"].acquire()
        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                command_exchange = create_exchange("command", connection)
                producer.publish(
                    "",
                    exchange=command_exchange,
                    routing_key="stop-{}".format(MODULE_NAME),
                    serializer="ujson",
                )
        shared_memory_locks["data_worker"].release()
        message = "instructed to stop"
        return message

    def post(self):
        """
        Instruct a service to start or stop by posting a command.
        Sample request body
        {
            "command": <start|stop>
        }
        :return: {"success": True|False, "message": <message>}
        """
        try:
            msg = json.loads(self.request.body)
            command = msg["command"]
            # start/stop data_worker
            if command == "start":
                message = self.start_data_worker()
                self.write({"success": True, "message": message})
            elif command == "stop":
                message = self.stop_data_worker()
                self.write({"success": True, "message": message})
            else:
                self.write({"success": False, "message": "unknown command"})
        except Exception:
            log.exception("Exception")
            self.write({"success": False, "message": "error during control"})


class Notifier:
    """
    Notifier Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["autoignore_rules"] = {}
        self.shared_memory_manager_dict["autoignore_prefix_tree"] = {"v4": {}, "v6": {}}
        self.shared_memory_manager_dict["autoignore_recalculate"] = True
        self.shared_memory_manager_dict["config_timestamp"] = -1

        log.info("service initiated")

    def make_rest_app(self):
        return Application(
            [
                (
                    "/config",
                    ConfigHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
                (
                    "/control",
                    ControlHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
                (
                    "/health",
                    HealthHandler,
                    dict(shared_memory_manager_dict=self.shared_memory_manager_dict),
                ),
            ]
        )

    def start_rest_app(self):
        app = self.make_rest_app()
        app.listen(REST_PORT)
        log.info("REST worker started and listening to port {}".format(REST_PORT))
        IOLoop.current().start()


class NotifierDataWorker(ConsumerProducerMixin):
    """
    RabbitMQ Consumer/Producer for this Service.
    """

    def __init__(
        self, connection: Connection, shared_memory_manager_dict: Dict
    ) -> NoReturn:
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.autoignore_prefix_tree = {
            "v4": pytricia.PyTricia(32),
            "v6": pytricia.PyTricia(128),
        }
        shared_memory_locks["autoignore"].acquire()
        if self.shared_memory_manager_dict["autoignore_recalculate"]:
            for ip_version in ["v4", "v6"]:
                if ip_version == "v4":
                    size = 32
                else:
                    size = 128
                self.autoignore_prefix_tree[ip_version] = dict_to_pytricia(
                    self.shared_memory_manager_dict["autoignore_prefix_tree"][
                        ip_version
                    ],
                    size,
                )
                log.info(
                    "{} pytricia tree parsed from configuration".format(ip_version)
                )
                self.shared_memory_manager_dict["autoignore_recalculate"] = False
        shared_memory_locks["autoignore"].release()

        # TODO: optional: set timers to periodically check for ongoing hijacks-to-be-ignored

        # EXCHANGES
        self.hijack_notification_exchange = create_exchange(
            "hijack-notification", connection, declare=True
        )
        self.command_exchange = create_exchange("command", connection, declare=True)

        # QUEUES
        self.hij_log_queue = create_queue(
            MODULE_NAME,
            exchange=self.hijack_notification_exchange,
            routing_key="hij-log",
            priority=1,
        )
        self.mail_log_queue = create_queue(
            MODULE_NAME,
            exchange=self.hijack_notification_exchange,
            routing_key="mail-log",
            priority=1,
        )
        self.stop_queue = create_queue(
            "{}-{}".format(MODULE_NAME, uuid()),
            exchange=self.command_exchange,
            routing_key="stop-{}".format(MODULE_NAME),
            priority=1,
        )

        log.info("data worker initiated")

    def get_consumers(self, Consumer: Consumer, channel: Connection) -> List[Consumer]:
        return [
            Consumer(
                queues=[self.hij_log_queue],
                on_message=self.handle_hij_log,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.mail_log_queue],
                on_message=self.handle_mail_log,
                prefetch_count=100,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.stop_queue],
                on_message=self.stop_consumer_loop,
                prefetch_count=100,
                accept=["ujson"],
            ),
        ]

    def find_autoignore_prefix_node(self, prefix):
        ip_version = get_ip_version(prefix)
        prefix_node = None
        shared_memory_locks["autoignore"].acquire()
        if ip_version == "v4":
            size = 32
        else:
            size = 128
        # need to turn to pytricia tree since this means that the tree has changed due to re-configuration
        if self.shared_memory_manager_dict["autoignore_recalculate"]:
            self.autoignore_prefix_tree[ip_version] = dict_to_pytricia(
                self.shared_memory_manager_dict["autoignore_prefix_tree"][ip_version],
                size,
            )
            log.info("{} pytricia tree re-parsed from configuration".format(ip_version))
            self.shared_memory_manager_dict["autoignore_recalculate"] = False
        if prefix in self.autoignore_prefix_tree[ip_version]:
            prefix_node = self.autoignore_prefix_tree[ip_version][prefix]
        shared_memory_locks["autoignore"].release()
        return prefix_node

    def hijack_suppressed(self, hijack: Dict):
        suppressed = False
        try:
            hijack_prefix = hijack["prefix"]
            hijack_num_peers_seen = len(hijack["peers_seen"])
            hijack_num_ases_infected = len(hijack["asns_inf"])
            autoignore_rule_match = self.find_autoignore_prefix_node(hijack_prefix)
            shared_memory_locks["autoignore"].acquire()
            if autoignore_rule_match:
                autoignore_rule_key = autoignore_rule_match["rule_key"]
                autoignore_rule = self.shared_memory_manager_dict["autoignore_rules"][
                    autoignore_rule_key
                ]
                thres_num_peers_seen = autoignore_rule["thres_num_peers_seen"]
                thres_num_ases_infected = autoignore_rule["thres_num_ases_infected"]
                if (hijack_num_peers_seen < thres_num_peers_seen) and (
                    hijack_num_ases_infected < thres_num_ases_infected
                ):
                    suppressed = True
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["autoignore"].release()
            return suppressed

    def handle_hij_log(self, message: Dict) -> NoReturn:
        """
        Callback function that generates a hijack log
        """
        message.ack()
        hij_dict = message.payload
        if not self.hijack_suppressed(hij_dict):
            hij_log.info(
                "{}".format(json.dumps(hijack_log_field_formatter(hij_dict))),
                extra={
                    "community_annotation": hij_dict.get("community_annotation", "NA")
                },
            )

    def handle_mail_log(self, message: Dict) -> NoReturn:
        """
        Callback function that generates a mail log
        """
        message.ack()
        hij_dict = message.payload
        if not self.hijack_suppressed(hij_dict):
            mail_log.info(
                "{}".format(json.dumps(hijack_log_field_formatter(hij_dict))),
                extra={
                    "community_annotation": hij_dict.get("community_annotation", "NA")
                },
            )

    def stop_consumer_loop(self, message: Dict) -> NoReturn:
        """
        Callback function that stop the current consumer loop
        """
        message.ack()
        self.should_stop = True


if __name__ == "__main__":
    # initiate notifier service with REST
    notifierService = Notifier()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_notifier(
            r.json(), notifierService.shared_memory_manager_dict
        )
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # start REST within main process
    notifierService.start_rest_app()
