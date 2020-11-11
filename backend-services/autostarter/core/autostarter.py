import os
import time

import requests
import ujson as json
from artemis_utils import DB_HOST
from artemis_utils import DB_NAME
from artemis_utils import DB_PASS
from artemis_utils import DB_PORT
from artemis_utils import DB_USER
from artemis_utils import get_logger
from artemis_utils.db_util import DB

# TODO: for user-controlled services, use this flag if the starter should set them
# from artemis_utils import AUTO_RECOVER_PROCESS_STATE

# logger
log = get_logger()

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 10))
CONFIGURATION_HOST = os.getenv("CONFIGURATION_HOST", "configuration")
DATABASE_HOST = os.getenv("DATABASE_HOST", "database")
FILEOBSERVER_HOST = os.getenv("FILEOBSERVER_HOST", "fileobserver")
PREFIXTREE_HOST = os.getenv("PREFIXTREE_HOST", "prefixtree")
RIPERISTAP_HOST = os.getenv("RIPERISTAP_HOST", "riperistap")
REST_PORT = int(os.getenv("REST_PORT", 3000))
ALWAYS_RUNNING_SERVICES = [
    CONFIGURATION_HOST,
    DATABASE_HOST,
    FILEOBSERVER_HOST,
    PREFIXTREE_HOST,
]
USER_CONTROLLED_SERVICES = [RIPERISTAP_HOST]


def bootstrap_intended_services(wo_db):
    query = (
        "INSERT INTO intended_process_states (name, running) "
        "VALUES (%s, %s) ON CONFLICT(name) DO NOTHING"
    )
    services_with_status = []
    for service in ALWAYS_RUNNING_SERVICES:
        services_with_status.append((service, True))
    # TODO: move to False after testing and let frontend set this at will
    for service in USER_CONTROLLED_SERVICES:
        services_with_status.append((service, True))
    wo_db.execute_batch(query, services_with_status)


def set_current_service_status(wo_db, service, running=False):
    query = (
        "INSERT INTO process_states (name, running) "
        "VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
        "SET running = EXCLUDED.running"
    )
    wo_db.execute(query, (service, running))


def check_and_control_services(ro_db, wo_db):
    query = "SELECT name, running FROM intended_process_states"
    entries = ro_db.execute(query)

    for entry in entries:
        try:
            service = entry[0]
            intended_status = entry[1]
            r = requests.get("http://{}:{}/health".format(service, REST_PORT))
            current_status = True if r.json()["status"] == "running" else False
            # ATTENTION: if response status is unconfigured, then the actual intention is False
            intended_status = (
                False if r.json()["status"] == "unconfigured" else intended_status
            )
            set_current_service_status(wo_db, service, current_status)
            if intended_status == current_status:
                # statuses match, do nothing
                # log.info("service '{}' data worker is at the intended state '{}'".format(
                #     service,
                #     r.json()["status"]
                # ))
                pass
            elif intended_status:
                log.info(
                    "service '{}' data worker should be running but is not".format(
                        service
                    )
                )
                r = requests.post(
                    url="http://{}:{}/control".format(service, REST_PORT),
                    data=json.dumps({"command": "start"}),
                )
                response = r.json()
                if not response["success"]:
                    raise Exception(response["message"])
                log.info("service '{}': '{}'".format(service, response["message"]))
            else:
                log.info(
                    "service '{}' data worker should not be running but it is".format(
                        service
                    )
                )
                r = requests.post(
                    url="http://{}:{}/control".format(service, REST_PORT),
                    data=json.dumps({"command": "stop"}),
                )
                response = r.json()
                if not response["success"]:
                    raise Exception(response["message"])
                log.info("service '{}': '{}'".format(service, response["message"]))
        except Exception:
            log.exception("exception")


if __name__ == "__main__":
    # DB variables
    # TODO: check if we should do these calls with gql instead of DB queries
    ro_db = DB(
        application_name="autostarter-readonly",
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        reconnect=True,
        autocommit=True,
        readonly=True,
    )
    wo_db = DB(
        application_name="autostarter-write",
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )

    # set always running service to true
    bootstrap_intended_services(wo_db)

    # control the processes that are intended to run or not in an endless loop
    while True:
        check_and_control_services(ro_db, wo_db)
        time.sleep(CHECK_INTERVAL)
