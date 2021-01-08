import multiprocessing as mp
import subprocess
import time
from typing import Dict
from typing import NoReturn

import ujson as json
from artemis_utils import get_logger
from artemis_utils.constants import DATABASE_HOST
from artemis_utils.constants import PREFIXTREE_HOST
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
shared_memory_locks = {"data_worker": mp.Lock()}

# global vars
SERVICE_NAME = "mitigation"
DATA_WORKER_DEPENDENCIES = [PREFIXTREE_HOST, DATABASE_HOST]


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Provides current configuration primitives (in the form of a JSON dict) to the requester.
        Note that mitigation does not have any actual configuration, since incoming
        messages come bundled with their own processing rules. It thus returns an empty dict.
        """
        self.write({})

    def post(self):
        """
        Pseudo-configures mitigation and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        self.write({"success": True, "message": "configured"})


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
                data_worker = MitigationDataWorker(
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


class Mitigation:
    """
    Mitigation Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["service_reconfiguring"] = False

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


class MitigationDataWorker(ConsumerProducerMixin):
    """
    RabbitMQ Consumer/Producer for the mitigation Service.
    """

    def __init__(self, connection, shared_memory_manager_dict):
        self.connection = connection
        self.shared_memory_manager_dict = shared_memory_manager_dict

        # wait for other needed data workers to start
        wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

        # EXCHANGES
        self.mitigation_exchange = create_exchange(
            "mitigation", connection, declare=True
        )
        self.command_exchange = create_exchange("command", connection, declare=True)

        # QUEUES
        self.mitigate_queue = create_queue(
            SERVICE_NAME,
            exchange=self.mitigation_exchange,
            routing_key="mitigate-with-action",
            priority=2,
        )
        self.unmitigate_queue = create_queue(
            SERVICE_NAME,
            exchange=self.mitigation_exchange,
            routing_key="unmitigate-with-action",
            priority=2,
        )
        self.stop_queue = create_queue(
            "{}-{}".format(SERVICE_NAME, uuid()),
            exchange=self.command_exchange,
            routing_key="stop-{}".format(SERVICE_NAME),
            priority=1,
        )

        log.info("data worker initiated")

    def get_consumers(self, Consumer, channel):
        return [
            Consumer(
                queues=[self.mitigate_queue],
                on_message=self.handle_mitigation_request,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.unmitigate_queue],
                on_message=self.handle_unmitigation_request,
                prefetch_count=1,
                accept=["ujson"],
            ),
            Consumer(
                queues=[self.stop_queue],
                on_message=self.stop_consumer_loop,
                prefetch_count=100,
                accept=["ujson"],
            ),
        ]

    def handle_mitigation_request(self, message):
        message.ack()
        mit_request = message.payload
        try:
            hijack_info = mit_request["hijack_info"]
            mitigation_action = mit_request["mitigation_action"]
            if isinstance(mitigation_action, list):
                mitigation_action = mitigation_action[0]
            if mitigation_action == "manual":
                log.info("starting manual mitigation of hijack {}".format(hijack_info))
            else:
                log.info(
                    "starting custom mitigation of hijack {} using '{}' script".format(
                        hijack_info, mitigation_action
                    )
                )
                hijack_info_str = json.dumps(hijack_info)
                subprocess.Popen(
                    [mitigation_action, "-i", hijack_info_str],
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            # do something
            mit_started = {"key": hijack_info["key"], "time": time.time()}
            self.producer.publish(
                mit_started,
                exchange=self.mitigation_exchange,
                routing_key="mit-start",
                priority=2,
                serializer="ujson",
            )
        except Exception:
            log.exception("exception")

    def handle_unmitigation_request(self, message):
        message.ack()
        unmit_request = message.payload
        try:
            hijack_info = unmit_request["hijack_info"]
            mitigation_action = unmit_request["mitigation_action"]
            if isinstance(mitigation_action, list):
                mitigation_action = mitigation_action[0]
            if mitigation_action == "manual":
                log.info("ending manual mitigation of hijack {}".format(hijack_info))
            else:
                log.info(
                    "ending custom mitigation of hijack {} using '{}' script".format(
                        hijack_info, mitigation_action
                    )
                )
                hijack_info_str = json.dumps(hijack_info)
                subprocess.Popen(
                    [mitigation_action, "-i", hijack_info_str, "-e"],
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            # do something
            mit_ended = {"key": hijack_info["key"], "time": time.time()}
            self.producer.publish(
                mit_ended,
                exchange=self.mitigation_exchange,
                routing_key="mit-end",
                priority=2,
                serializer="ujson",
            )
        except Exception:
            log.exception("exception")

    def stop_consumer_loop(self, message: Dict) -> NoReturn:
        """
        Callback function that stop the current consumer loop
        """
        message.ack()
        self.should_stop = True


def main():
    # initiate mitigation service with REST
    mitigationService = Mitigation()

    # start REST within main process
    mitigationService.start_rest_app()


if __name__ == "__main__":
    main()
