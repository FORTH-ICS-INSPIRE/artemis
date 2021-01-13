import difflib
import multiprocessing as mp
import time

import requests
import ujson as json
from artemis_utils import get_logger
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.envvars import REST_PORT
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchObserver

# logger
log = get_logger()

# shared memory object locks
shared_memory_locks = {"data_worker": mp.Lock()}

# global vars
SERVICE_NAME = "fileobserver"


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def initialize(self, shared_memory_manager_dict):
        self.shared_memory_manager_dict = shared_memory_manager_dict

    def get(self):
        """
        Provides current configuration primitives (in the form of a JSON dict) to the requester.
        Note that autoignore does not have any actual configuration, but we return the following
        information that it uses to operate:
        {
            "dirname": <string>,
            "filename": <string>
        }
        """
        self.write(
            {
                "dirname": self.shared_memory_manager_dict["dirname"],
                "filename": self.shared_memory_manager_dict["filename"],
            }
        )

    def post(self):
        """
        Pseudo-configures fileobserver and responds with a success message.
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
        shared_memory_locks["data_worker"].acquire()
        observer = WatchObserver()
        try:
            event_handler = Handler(
                self.shared_memory_manager_dict["dirname"],
                self.shared_memory_manager_dict["filename"],
            )
            observer.schedule(
                event_handler,
                self.shared_memory_manager_dict["dirname"],
                recursive=False,
            )
            observer.start()
            self.shared_memory_manager_dict["data_worker_running"] = True
            shared_memory_locks["data_worker"].release()
            log.info("data worker started")
            while True:
                time.sleep(5)
                if not self.shared_memory_manager_dict["data_worker_running"]:
                    break
        except Exception:
            log.exception("exception")
            shared_memory_locks["data_worker"].release()
        finally:
            observer.stop()
            observer.join()
            shared_memory_locks["data_worker"].acquire()
            self.shared_memory_manager_dict["data_worker_running"] = False
            shared_memory_locks["data_worker"].release()
            log.info("data worker stopped")

    def stop_data_worker(self):
        shared_memory_locks["data_worker"].acquire()
        self.shared_memory_manager_dict["data_worker_running"] = False
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


class FileObserver:
    """
    FileObserver REST Service.
    """

    def __init__(self):
        # initialize shared memory
        shared_memory_manager = mp.Manager()
        self.shared_memory_manager_dict = shared_memory_manager.dict()
        self.shared_memory_manager_dict["data_worker_running"] = False
        self.shared_memory_manager_dict["service_reconfiguring"] = False
        self.shared_memory_manager_dict["dirname"] = "/etc/artemis"
        self.shared_memory_manager_dict["filename"] = "config.yaml"

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


class Handler(FileSystemEventHandler):
    def __init__(self, d, fn):
        super().__init__()
        self.response = None
        self.path = "{}/{}".format(d, fn)
        try:
            with open(self.path, "r") as f:
                self.content = f.readlines()
        except Exception:
            log.exception("exception")

    def on_modified(self, event):
        if event.is_directory:
            return None

        if event.src_path == self.path:
            self.check_changes()

    def on_moved(self, event):
        if event.is_directory:
            return None

        if event.dest_path == self.path:
            self.check_changes()

    def check_changes(self):
        with open(self.path, "r") as f:
            content = f.readlines()
        changes = "".join(difflib.unified_diff(self.content, content))
        if changes:
            try:
                r = requests.post(
                    url="http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT),
                    data=json.dumps(
                        {"type": "yaml", "content": content, "origin": "fileobserver"}
                    ),
                )
                response = r.json()

                if response["success"]:
                    if response["message"] == "ignored":
                        text = "new configuration ok but ignored (no need to change)"
                    else:
                        text = "new configuration accepted:\n{}".format(changes)
                    log.info(text)
                    self.content = content
                else:
                    log.error(
                        "invalid configuration due to error '{}':\n{}".format(
                            response["message"], content
                        )
                    )
            except Exception:
                log.error(
                    "could not send configuration to service '{}'".format(
                        CONFIGURATION_HOST
                    )
                )


def make_app():
    return Application(
        [
            ("/config", ConfigHandler),
            ("/control", ControlHandler),
            ("/health", HealthHandler),
        ]
    )


def main():
    # initiate file observer service with REST
    fileObserverService = FileObserver()

    # start REST within main process
    fileObserverService.start_rest_app()


if __name__ == "__main__":
    main()
