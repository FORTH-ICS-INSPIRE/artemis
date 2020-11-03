import threading

import ujson as json
from tornado.web import RequestHandler

from . import get_logger


# global vars for data tasks and corresponding RMQ threads in containers
data_task = None
data_task_thread = None

log = get_logger()


def setup_data_task(data_task_class, **kwargs):
    global data_task
    if data_task is None:
        data_task = data_task_class(**kwargs)
    elif data_task.is_running():
        stop_data_task()
        data_task = data_task_class(**kwargs)
        start_data_task()
    else:
        data_task = data_task_class(**kwargs)
    log.info("data task set up")


def start_data_task():
    global data_task
    global data_task_thread
    if data_task is None:
        log.error("attempting to start unconfigured data task")
        return
    if data_task.is_running():
        log.info("data task is already running")
        return
    data_task_thread = threading.Thread(target=data_task.run)
    data_task_thread.start()
    log.info("data task started")


def stop_data_task():
    global data_task
    global data_task_thread
    if data_task is not None and data_task_thread is not None and data_task.is_running:
        data_task.stop()
        data_task_thread.join()
    log.info("data task stopped")


class ControlHandler(RequestHandler):
    """
    REST request handler for control commands.
    """

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
            global data_task
            msg = json.loads(self.request.body)
            command = msg["command"]
            # start/stop data_task
            if command == "start":
                start_data_task()
                self.write({"success": True, "message": "command applied"})
            elif command == "stop":
                stop_data_task()
                self.write({"success": True, "message": "command applied"})
            else:
                self.write({"success": False, "message": "unknown command"})
        except Exception:
            log.exception("Exception")
            self.write({"success": False, "message": "error during control"})


class HealthHandler(RequestHandler):
    """
    REST request handler for health checks.
    """

    def get(self):
        """
        Extract the status of a service via a GET request.
        :return: {"status" : <unconfigured|running|stopped>}
        """
        global data_task
        status = "stopped"
        if data_task is None:
            status = "unconfigured"
        elif data_task.is_running():
            status = "running"
        self.write({"status": status})
