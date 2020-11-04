import difflib
import time

import artemis_utils.rest_util
import requests
import ujson as json
from artemis_utils import get_logger
from artemis_utils import signal_loading
from artemis_utils.rest_util import ControlHandler
from artemis_utils.rest_util import HealthHandler
from artemis_utils.rest_util import setup_data_task
from artemis_utils.rest_util import start_data_task
from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.web import RequestHandler
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchObserver

log = get_logger()
MODULE_NAME = "fileobserver"
# TODO: add the following in utils
CONFIGURATION_HOST = "configuration"
REST_PORT = 3000


class ConfigHandler(RequestHandler):
    """
    REST request handler for configuration.
    """

    def post(self):
        """
        Configures fileobserver and responds with a success message.
        :return: {"success": True | False, "message": < message >}
        """
        self.write({"success": True, "message": "configured"})


class FileObserver:
    """
    FileObserver Service.
    """

    def __init__(self):
        self._running = False

    def is_running(self):
        return self._running

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        observer = WatchObserver()
        dirname = "/etc/artemis"
        filename = "config.yaml"

        try:
            event_handler = self.Handler(dirname, filename)
            observer.schedule(event_handler, dirname, recursive=False)
            observer.start()
            log.info("started")
            while self._running:
                time.sleep(5)
        except Exception:
            log.exception("exception")
        finally:
            observer.stop()
            observer.join()
            log.info("stopped")
            self._running = False

    class Handler(FileSystemEventHandler):
        def __init__(self, d, fn):
            super().__init__()
            signal_loading(MODULE_NAME, True)
            self.response = None
            self.path = "{}/{}".format(d, fn)
            try:
                with open(self.path, "r") as f:
                    self.content = f.readlines()
            except Exception:
                log.exception("exception")
            finally:
                signal_loading(MODULE_NAME, False)

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
                        data=json.dumps({"type": "yaml", "content": content}),
                    )
                    response = r.json()

                    if response["success"]:
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
                    log.exception("exception")


def make_app():
    return Application(
        [
            ("/config", ConfigHandler),
            ("/control", ControlHandler),
            ("/health", HealthHandler),
        ]
    )


if __name__ == "__main__":
    # fileobserver should be initiated in any case
    setup_data_task(FileObserver)

    # fileobserver should start in any case
    start_data_task()
    while not artemis_utils.rest_util.data_task.is_running():
        time.sleep(1)

    # create REST worker
    app = make_app()
    app.listen(REST_PORT)
    log.info("Listening to port {}".format(REST_PORT))
    IOLoop.current().start()
