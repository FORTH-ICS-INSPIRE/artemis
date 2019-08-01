import logging
import time
from xmlrpc.client import ServerProxy

from webapp.utils import BACKEND_SUPERVISOR_URI
from webapp.utils import MON_SUPERVISOR_URI

log = logging.getLogger("webapp_logger")

intervals = (
    ("W", 604800),  # 60 * 60 * 24 * 7
    ("D", 86400),  # 60 * 60 * 24
    ("H", 3600),  # 60 * 60
    ("M", 60),
    ("S", 1),
)


def display_time(seconds, granularity=2):
    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip("s")
            result.append("{} {}".format(int(value), name))
    return ", ".join(result[:granularity])


class Modules_state:
    def __init__(self):
        self.backend_server = ServerProxy(BACKEND_SUPERVISOR_URI)
        self.mon_server = ServerProxy(MON_SUPERVISOR_URI)

    def call(self, module, action):
        try:
            if module == "all":
                if action == "start":
                    for ctx in {self.backend_server, self.mon_server}:
                        ctx.supervisor.startAllProcesses()
                elif action == "stop":
                    for ctx in {self.backend_server, self.mon_server}:
                        ctx.supervisor.stopAllProcesses()
            else:
                log.info(module)
                ctx = self.backend_server
                if module == "monitor":
                    ctx = self.mon_server

                if action == "start":
                    modules = self.is_any_up_or_running(module, up=False)
                    for mod in modules:
                        ctx.supervisor.startProcess(mod)

                elif action == "stop":
                    modules = self.is_any_up_or_running(module)
                    for mod in modules:
                        ctx.supervisor.stopProcess(mod)
        except Exception:
            log.exception("exception")

    def is_up_or_running(self, module):
        ctx = self.backend_server
        if module == "monitor":
            ctx = self.mon_server

        try:
            state = ctx.supervisor.getProcessInfo(module)["state"]
            while state == 10:
                time.sleep(0.5)
                state = ctx.supervisor.getProcessInfo(module)["state"]
            return state == 20
        except Exception:
            log.exception("exception")
            return False

    def is_any_up_or_running(self, module, up=True):
        ctx = self.backend_server
        if module == "monitor":
            ctx = self.mon_server

        try:
            if up:
                return [
                    "{}:{}".format(x["group"], x["name"])
                    for x in ctx.supervisor.getAllProcessInfo()
                    if x["group"] == module and (x["state"] == 20 or x["state"] == 10)
                ]
            return [
                "{}:{}".format(x["group"], x["name"])
                for x in ctx.supervisor.getAllProcessInfo()
                if x["group"] == module and (x["state"] != 20 and x["state"] != 10)
            ]
        except Exception:
            log.exception("exception")
            return False

    def get_response_all(self):
        ret_response = {}
        for ctx in {self.backend_server, self.mon_server}:
            response = ctx.supervisor.getAllProcessInfo()
            for module in response:
                if module["state"] == 20:
                    ret_response[module["name"]] = {
                        "status": "up",
                        "uptime": display_time(module["now"] - module["start"]),
                    }
                else:
                    ret_response[module["name"]] = {"status": "down", "uptime": "N/A"}
        return ret_response

    def get_response_formatted_all(self):
        return self.get_response_all()
