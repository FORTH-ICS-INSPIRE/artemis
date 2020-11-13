import logging

import requests
from flask_jwt_extended import create_access_token
from flask_security import current_user
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from webapp.utils import CONFIGURATION_HOST
from webapp.utils import DATABASE_HOST
from webapp.utils import FILEOBSERVER_HOST
from webapp.utils import GRAPHQL_URI
from webapp.utils import NOTIFIER_HOST
from webapp.utils import PREFIXTREE_HOST
from webapp.utils import REST_PORT

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

USER_CONTROLLED_MODULES = ["monitor", "detection", "mitigation"]
ALWAYS_ON_MODULES = [
    CONFIGURATION_HOST,
    DATABASE_HOST,
    FILEOBSERVER_HOST,
    PREFIXTREE_HOST,
    NOTIFIER_HOST,
]


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
        pass

    # TODO: refactor this
    def call(self, module, action):
        # try:
        #     if module == "all":
        #         if action == "start":
        #             for ctx in {self.backend_server, self.mon_server}:
        #                 ctx.supervisor.startAllProcesses()
        #         elif action == "stop":
        #             for ctx in {self.backend_server, self.mon_server}:
        #                 ctx.supervisor.stopAllProcesses()
        #     else:
        #         log.info(module)
        #         ctx = self.backend_server
        #         if module == "monitor":
        #             ctx = self.mon_server
        #
        #         if action == "start":
        #             modules = self.is_any_up_or_running(module, up=False)
        #             for mod in modules:
        #                 ctx.supervisor.startProcess(mod)
        #                 if module in user_controlled_modules:
        #                     self.update_intended_process_states(
        #                         name=module, running=True
        #                     )
        #
        #         elif action == "stop":
        #             modules = self.is_any_up_or_running(module)
        #             for mod in modules:
        #                 ctx.supervisor.stopProcess(mod)
        #                 if module in user_controlled_modules:
        #                     self.update_intended_process_states(
        #                         name=module, running=False
        #                     )
        #
        # except Exception:
        #     log.exception("exception")
        return False

    def is_up_or_running(self, module):
        try:
            r = requests.get("http://{}:{}/health".format(module, REST_PORT))
            return r.json()["status"] == "running"
        except Exception:
            log.exception("exception")
            return False

    # TODO: refactor this
    def is_any_up_or_running(self, module, up=True):
        # ctx = self.backend_server
        # if module == "monitor":
        #     ctx = self.mon_server
        #
        # try:
        #     if up:
        #         return [
        #             "{}:{}".format(x["group"], x["name"])
        #             for x in ctx.supervisor.getAllProcessInfo()
        #             if x["group"] == module and (x["state"] == 20 or x["state"] == 10)
        #         ]
        #     return [
        #         "{}:{}".format(x["group"], x["name"])
        #         for x in ctx.supervisor.getAllProcessInfo()
        #         if x["group"] == module and (x["state"] != 20 and x["state"] != 10)
        #     ]
        # except Exception:
        #     log.exception("exception")
        #     return False
        return self.is_up_or_running("module")

    # TODO: refactor this
    def get_response_all(self):
        ret_response = {}
        # for ctx in {self.backend_server, self.mon_server}:
        #     response = ctx.supervisor.getAllProcessInfo()
        #     for module in response:
        #         if module["state"] == 20:
        #             ret_response[module["name"]] = {
        #                 "status": "up",
        #                 "uptime": display_time(module["now"] - module["start"]),
        #             }
        #         else:
        #             ret_response[module["name"]] = {"status": "down", "uptime": "N/A"}
        for module in ALWAYS_ON_MODULES + USER_CONTROLLED_MODULES:
            try:
                r = requests.get("http://{}:{}/health".format(module, REST_PORT))
                ret_response["module"] = {
                    "status": "up" if r.json()["status"] == "running" else "down",
                    "uptime": "N/A",
                }
            except Exception:
                ret_response["module"] = {"status": "down", "uptime": "N/A"}
        return ret_response

    def get_response_formatted_all(self):
        return self.get_response_all()

    def update_intended_process_states(self, name, running=False):
        try:
            access_token = create_access_token(identity=current_user)
            transport = RequestsHTTPTransport(
                url=GRAPHQL_URI,
                use_json=True,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": "Bearer {}".format(access_token),
                },
                verify=False,
            )

            client = Client(
                retries=3, transport=transport, fetch_schema_from_transport=True
            )

            query = gql(intended_process_states_mutation)

            params = {"name": name, "running": running}

            client.execute(query, variable_values=params)

        except Exception:
            log.exception("exception")
