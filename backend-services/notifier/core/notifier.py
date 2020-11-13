import logging
import multiprocessing as mp
import os
from typing import Dict
from typing import List
from typing import NoReturn

import ujson as json
from artemis_utils import get_logger
from artemis_utils import hijack_log_field_formatter
from artemis_utils import RABBITMQ_URI
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Consumer
from kombu import Producer
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
shared_memory_locks = {"data_worker": mp.Lock()}

# global vars
MODULE_NAME = os.getenv("MODULE_NAME", "prefixtree")
REST_PORT = int(os.getenv("REST_PORT", 3000))


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def post(self):
        """
        Simply responds with a success message (nothing else needed here).
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
            MODULE_NAME,
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

    @staticmethod
    def handle_hij_log(message: Dict) -> NoReturn:
        """
        Callback function that generates a hijack log
        """
        message.ack()
        hij_log_msg = message.payload
        hij_log.info(
            "{}".format(json.dumps(hijack_log_field_formatter(hij_log_msg))),
            extra={
                "community_annotation": hij_log_msg.get("community_annotation", "NA")
            },
        )

    @staticmethod
    def handle_mail_log(message: Dict) -> NoReturn:
        """
        Callback function that generates a mail log
        """
        message.ack()
        mail_log_msg = message.payload
        mail_log.info(
            "{}".format(json.dumps(hijack_log_field_formatter(mail_log_msg))),
            extra={
                "community_annotation": mail_log_msg.get("community_annotation", "NA")
            },
        )

    def stop_consumer_loop(self, message: Dict) -> NoReturn:
        """
        Callback function that stop the current consumer loop
        """
        message.ack()
        self.should_stop = True

    # TODO: encapsulate auto-ignore functionality (before alerts are propagated to the user)


if __name__ == "__main__":
    # initiate notifier service with REST
    notifierService = Notifier()

    # start REST within main process
    notifierService.start_rest_app()
