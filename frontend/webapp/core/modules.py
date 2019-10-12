import json
import logging
import time
from xmlrpc.client import ServerProxy

import requests
from flask_jwt_extended import create_access_token
from flask_security import current_user
from webapp.utils import BACKEND_SUPERVISOR_URI
from webapp.utils import GRAPHQL_URI
from webapp.utils import MON_SUPERVISOR_URI


log = logging.getLogger("artemis_logger")

intervals = (
    ("W", 604800),  # 60 * 60 * 24 * 7
    ("D", 86400),  # 60 * 60 * 24
    ("H", 3600),  # 60 * 60
    ("M", 60),
    ("S", 1),
)

intended_process_states_mutation = """
mutation updateIntendedProcessStates($name: String, $running: Boolean) {
  update_view_intended_process_states(where: {name: {_eq: $name}}, _set: {running: $running}) {
    affected_rows
    returning {
      name
      running
    }
  }
}
"""

user_controlled_modules = ["monitor", "detection", "mitigation"]


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
                        if module in user_controlled_modules:
                            self.update_intended_process_states(
                                name=module, running=True
                            )

                elif action == "stop":
                    modules = self.is_any_up_or_running(module)
                    for mod in modules:
                        ctx.supervisor.stopProcess(mod)
                        if module in user_controlled_modules:
                            self.update_intended_process_states(
                                name=module, running=False
                            )

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

    def update_intended_process_states(self, name, running=False):
        try:
            access_token = create_access_token(identity=current_user)
            graqphql_request_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer {}".format(access_token),
            }
            graqphql_request_payload = json.dumps(
                {
                    "variables": {"name": name, "running": running},
                    "operationName": "updateIntendedProcessStates",
                    "query": intended_process_states_mutation,
                }
            )
            requests.post(
                url=GRAPHQL_URI,
                headers=graqphql_request_headers,
                data=graqphql_request_payload,
            )
        except Exception:
            log.exception("exception")
