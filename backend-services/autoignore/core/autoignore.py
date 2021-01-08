import multiprocessing as mp
import time
from typing import Dict
from typing import NoReturn

import requests
import ujson as json
from artemis_utils import get_logger
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.constants import DATABASE_HOST
from artemis_utils.constants import PREFIXTREE_HOST
from artemis_utils.db import DB
from artemis_utils.envvars import DB_HOST
from artemis_utils.envvars import DB_NAME
from artemis_utils.envvars import DB_PASS
from artemis_utils.envvars import DB_PORT
from artemis_utils.envvars import DB_USER
from artemis_utils.envvars import RABBITMQ_URI
from artemis_utils.envvars import REST_PORT
from artemis_utils.rabbitmq import create_exchange
from artemis_utils.rabbitmq import create_queue
from artemis_utils.service import wait_data_worker_dependencies
from kombu import Connection
from kombu import Producer
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler

# logger
log = get_logger()

# shared memory object locks
shared_memory_locks = {
    "data_worker": mp.Lock(),
    "autoignore": mp.Lock(),
    "ongoing_hijacks": mp.Lock(),
    "config_timestamp": mp.Lock(),
    "time": mp.Lock(),
    "service_reconfiguring": mp.Lock(),
}

# global vars
SERVICE_NAME = "autoignore"
DATA_WORKER_DEPENDENCIES = [PREFIXTREE_HOST, DATABASE_HOST]


def configure_autoignore(msg, shared_memory_manager_dict):
    config = msg
    try:
        # check newer config
        config_timestamp = shared_memory_manager_dict["config_timestamp"]
        if config["timestamp"] > config_timestamp:
            shared_memory_locks["service_reconfiguring"].acquire()
            shared_memory_manager_dict["service_reconfiguring"] = True
            shared_memory_locks["service_reconfiguring"].release()

            # extract autoignore rules
            autoignore_rules = config.get("autoignore", {})
            for key in autoignore_rules:
                # prefixes are not needed and should not be expanded (handled by prefix tree)
                del autoignore_rules[key]["prefixes"]

            shared_memory_locks["autoignore"].acquire()
            shared_memory_manager_dict["autoignore_rules"] = autoignore_rules
            shared_memory_locks["autoignore"].release()

            shared_memory_locks["config_timestamp"].acquire()
            shared_memory_manager_dict["config_timestamp"] = config["timestamp"]
            shared_memory_locks["config_timestamp"].release()

            shared_memory_locks["time"].acquire()
            shared_memory_manager_dict["time"] = 0
            shared_memory_locks["time"].release()

        shared_memory_locks["service_reconfiguring"].acquire()
        shared_memory_manager_dict["service_reconfiguring"] = False
        shared_memory_locks["service_reconfiguring"].release()
        return {"success": True, "message": "configured"}
    except Exception:
        log.exception("exception")
        shared_memory_locks["service_reconfiguring"].acquire()
        shared_memory_manager_dict["service_reconfiguring"] = False
        shared_memory_locks["service_reconfiguring"].release()
        return {"success": False, "message": "error during service configuration"}


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Provides current configuration primitives (in the form of a JSON dict) to the requester.
        Format:
        {
            "autoignore_rules": <dict>,
            "config_timestamp": <timestamp>
        }
        """
        ret_dict = {}

        ret_dict["autoignore_rules"] = self.shared_memory_manager_dict[
            "autoignore_rules"
        ]

        ret_dict["config_timestamp"] = self.shared_memory_manager_dict[
            "config_timestamp"
        ]

        self.write(ret_dict)

    def post(self):
        """
        Configures autoignore and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        try:
            msg = json.loads(self.request.body)
            self.write(configure_autoignore(msg, self.shared_memory_manager_dict))
        except Exception:
            self.write(
                {"success": False, "message": "error during service configuration"}
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
        :return: {"status" : <unconfigured|running|stopped><,reconfiguring>}
        """
        status = "stopped"
        shared_memory_locks["data_worker"].acquire()
        if self.shared_memory_manager_dict["data_worker_running"]:
            status = "running"
        shared_memory_locks["data_worker"].release()
        if self.shared_memory_manager_dict["service_reconfiguring"]:
            status += ",reconfiguring"
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
                data_worker = AutoignoreDataWorker(
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
        try:
            with Connection(RABBITMQ_URI) as connection:
                with Producer(connection) as producer:
                    command_exchange = create_exchange("command", connection)
                    producer.publish(
                        "",
                        exchange=command_exchange,
                        routing_key="stop-{}".format(SERVICE_NAME),
                        serializer="ujson",
                    )
        except Exception:
            log.exception("exception")
        finally:
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


class Autoignore:
    """
    Autoignore Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["service_reconfiguring"] = False
        self.shared_memory_manager_dict["autoignore_rules"] = {}
        self.shared_memory_manager_dict["config_timestamp"] = -1
        self.shared_memory_manager_dict["time"] = 0
        self.shared_memory_manager_dict["ongoing_hijacks"] = {}

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


class AutoignoreChecker:
    """
    Autoignore checker.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict

        # DB variables
        self.ro_db = DB(
            application_name="autoignore-checker-readonly",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            reconnect=True,
            autocommit=True,
            readonly=True,
        )

        # EXCHANGES
        self.autoignore_exchange = create_exchange(
            "autoignore", connection, declare=True
        )

    def check_rules_should_be_checked(self):
        ongoing_hijacks_to_prefixes = {}
        # check if we need to ask prefixtree about potential rule match
        shared_memory_locks["autoignore"].acquire()
        try:
            for key in self.shared_memory_manager_dict["autoignore_rules"]:
                interval = int(
                    self.shared_memory_manager_dict["autoignore_rules"][key]["interval"]
                )
                if interval <= 0:
                    continue
                shared_memory_locks["time"].acquire()
                self.shared_memory_manager_dict["time"] += 1
                process_time = self.shared_memory_manager_dict["time"]
                shared_memory_locks["time"].release()
                if process_time % interval == 0:
                    # do the following once for the current session
                    if len(ongoing_hijacks_to_prefixes) == 0:
                        shared_memory_locks["ongoing_hijacks"].acquire()
                        try:
                            # fetch ongoing hijack events
                            query = (
                                "SELECT time_started, time_last, num_peers_seen, "
                                "num_asns_inf, key, prefix, hijack_as, type, time_detected "
                                "FROM hijacks WHERE active = true"
                            )
                            entries = self.ro_db.execute(query)
                            ongoing_hijacks = {}
                            for entry in entries:
                                ongoing_hijacks[entry[4]] = {
                                    "prefix": entry[5],
                                    "time_last_updated": max(
                                        int(entry[1].timestamp()),
                                        int(entry[8].timestamp()),
                                    ),
                                    "num_peers_seen": int(entry[2]),
                                    "num_asns_inf": int(entry[3]),
                                    "hijack_as": int(entry[6]),
                                    "hij_type": entry[7],
                                }
                                ongoing_hijacks_to_prefixes[entry[4]] = entry[5]
                            self.shared_memory_manager_dict[
                                "ongoing_hijacks"
                            ] = ongoing_hijacks
                        except Exception:
                            log.exception("exception")
                        finally:
                            shared_memory_locks["ongoing_hijacks"].release()

                    if len(ongoing_hijacks_to_prefixes) > 0:
                        with Producer(self.connection) as producer:
                            producer.publish(
                                {
                                    "ongoing_hijacks_to_prefixes": ongoing_hijacks_to_prefixes,
                                    "rule_key": key,
                                },
                                exchange=self.autoignore_exchange,
                                routing_key="ongoing-hijack-prefixes",
                                serializer="ujson",
                            )
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["autoignore"].release()

    def run(self):
        while True:
            # stop if parent is not running any more
            shared_memory_locks["data_worker"].acquire()
            if not self.shared_memory_manager_dict["data_worker_running"]:
                shared_memory_locks["data_worker"].release()
                break
            shared_memory_locks["data_worker"].release()
            self.check_rules_should_be_checked()
            time.sleep(1)


class AutoignoreDataWorker(ConsumerProducerMixin):
    """
    RabbitMQ Consumer/Producer for the autoignore Service.
    """

    def __init__(
        self, connection: Connection, shared_memory_manager_dict: Dict
    ) -> NoReturn:
        self.connection = connection
        self.rule_timer_thread = None
        self.shared_memory_manager_dict = shared_memory_manager_dict

        # wait for other needed data workers to start
        wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

        # EXCHANGES
        self.autoignore_exchange = create_exchange(
            "autoignore", connection, declare=True
        )
        self.hijack_exchange = create_exchange(
            "hijack-update", connection, declare=True
        )
        self.command_exchange = create_exchange("command", connection, declare=True)

        # QUEUES
        self.autoignore_hijacks_rules_queue = create_queue(
            SERVICE_NAME,
            exchange=self.autoignore_exchange,
            routing_key="hijacks-matching-rule",
            priority=1,
        )
        self.stop_queue = create_queue(
            "{}-{}".format(SERVICE_NAME, uuid()),
            exchange=self.command_exchange,
            routing_key="stop-{}".format(SERVICE_NAME),
            priority=1,
        )

        # DB variables
        self.ro_db = DB(
            application_name="autoignore-data-worker-readonly",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            reconnect=True,
            autocommit=True,
            readonly=True,
        )

        log.info("setting up autoignore checker process...")
        self.autoignore_checker = AutoignoreChecker(
            self.connection, self.shared_memory_manager_dict
        )
        mp.Process(target=self.autoignore_checker.run).start()
        log.info("autoignore checker set up")

        log.info("data worker initiated")

    def get_consumers(self, Consumer, channel):
        return [
            Consumer(
                queues=[self.autoignore_hijacks_rules_queue],
                on_message=self.handle_autoignore_hijacks_matching_rule,
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

    def handle_autoignore_hijacks_matching_rule(self, message):
        message.ack()
        payload = message.payload
        shared_memory_locks["ongoing_hijacks"].acquire()
        try:
            hijacks_matching_rule = set(payload["hijacks_matching_rule"])
            if len(hijacks_matching_rule) == 0:
                return
            rule_key = payload["rule_key"]
            shared_memory_locks["autoignore"].acquire()
            rule = self.shared_memory_manager_dict["autoignore_rules"].get(
                rule_key, None
            )
            shared_memory_locks["autoignore"].release()

            if not rule:
                return

            thres_num_peers_seen = rule["thres_num_peers_seen"]
            thres_num_ases_infected = rule["thres_num_ases_infected"]
            interval = rule["interval"]

            time_now = int(time.time())
            ongoing_hijacks = self.shared_memory_manager_dict["ongoing_hijacks"]
            for hijack_key in hijacks_matching_rule:
                if hijack_key not in ongoing_hijacks:
                    continue

                hijack_prefix = ongoing_hijacks[hijack_key]["prefix"]
                hijack_type = ongoing_hijacks[hijack_key]["hij_type"]
                hijack_as = ongoing_hijacks[hijack_key]["hijack_as"]
                hijack_num_peers_seen = ongoing_hijacks[hijack_key]["num_peers_seen"]
                hijack_num_ases_infected = ongoing_hijacks[hijack_key]["num_asns_inf"]
                time_last_updated = ongoing_hijacks[hijack_key]["time_last_updated"]

                if (
                    (time_now - time_last_updated > interval)
                    and (hijack_num_peers_seen < thres_num_peers_seen)
                    and (hijack_num_ases_infected < thres_num_ases_infected)
                ):
                    self.producer.publish(
                        {
                            "key": hijack_key,
                            "prefix": hijack_prefix,
                            "type": hijack_type,
                            "hijack_as": hijack_as,
                        },
                        exchange=self.hijack_exchange,
                        routing_key="ignore",
                        priority=2,
                        serializer="ujson",
                    )
        except Exception:
            log.exception("exception")
        finally:
            shared_memory_locks["ongoing_hijacks"].release()

    def stop_consumer_loop(self, message: Dict) -> NoReturn:
        """
        Callback function that stop the current consumer loop
        """
        message.ack()
        self.should_stop = True


def main():
    # initiate autoignore service with REST
    autoignoreService = Autoignore()

    # try to get configuration upon start (it is OK if it fails, will get it from POST)
    # (this is needed because service may restart while configuration is running)
    try:
        r = requests.get("http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT))
        conf_res = configure_autoignore(
            r.json(), autoignoreService.shared_memory_manager_dict
        )
        if not conf_res["success"]:
            log.info(
                "could not get configuration upon startup, will get via POST later"
            )
    except Exception:
        log.info("could not get configuration upon startup, will get via POST later")

    # start REST within main process
    autoignoreService.start_rest_app()


if __name__ == "__main__":
    main()
