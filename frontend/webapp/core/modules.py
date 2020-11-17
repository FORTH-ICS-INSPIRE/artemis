import logging

import requests
from flask_jwt_extended import create_access_token
from flask_security import current_user
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from webapp.utils import CONFIGURATION_HOST
from webapp.utils import DATABASE_HOST
from webapp.utils import DETECTION_HOST
from webapp.utils import FILEOBSERVER_HOST
from webapp.utils import GRAPHQL_URI
from webapp.utils import MITIGATION_HOST
from webapp.utils import NOTIFIER_HOST
from webapp.utils import PREFIXTREE_HOST
from webapp.utils import REST_PORT
from webapp.utils import RIPERISTAP_HOST

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

USER_CONTROLLED_MODULES = [RIPERISTAP_HOST, DETECTION_HOST, MITIGATION_HOST]
MONITOR_MODULES = [RIPERISTAP_HOST]
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

    def call(self, module, action):
        try:
            if module == "all":
                for service in ALWAYS_ON_MODULES + USER_CONTROLLED_MODULES:
                    self.update_intended_process_states(service, action == "start")
            else:
                if module == "monitor":
                    for mod in MONITOR_MODULES:
                        self.update_intended_process_states(mod, action == "start")
                elif module in USER_CONTROLLED_MODULES:
                    self.update_intended_process_states(module, action == "start")
            return True
        except Exception:
            log.exception("exception")
            return False
        return False

    def is_up_or_running(self, module):
        try:
            r = requests.get("http://{}:{}/health".format(module, REST_PORT))
            return r.json()["status"] == "running"
        except Exception:
            log.exception("exception")
            return False

    @staticmethod
    def update_intended_process_states(name, running=False):
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
