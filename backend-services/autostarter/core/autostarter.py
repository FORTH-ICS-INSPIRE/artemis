import os
import re
import socket
import time

import requests
import ujson as json
from artemis_utils import AUTO_RECOVER_PROCESS_STATE
from artemis_utils import DB_HOST
from artemis_utils import DB_NAME
from artemis_utils import DB_PASS
from artemis_utils import DB_PORT
from artemis_utils import DB_USER
from artemis_utils import get_logger
from artemis_utils.db_util import DB

# logger
log = get_logger()

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))
CONFIGURATION_HOST = os.getenv("CONFIGURATION_HOST", "configuration")
DATABASE_HOST = os.getenv("DATABASE_HOST", "database")
FILEOBSERVER_HOST = os.getenv("FILEOBSERVER_HOST", "fileobserver")
PREFIXTREE_HOST = os.getenv("PREFIXTREE_HOST", "prefixtree")
NOTIFIER_HOST = os.getenv("NOTIFIER_HOST", "notifier")
DETECTION_HOST = os.getenv("DETECTION_HOST", "detection")
MITIGATION_HOST = os.getenv("MITIGATION_HOST", "mitigation")
RIPERISTAP_HOST = os.getenv("RIPERISTAP_HOST", "riperistap")
REST_PORT = int(os.getenv("REST_PORT", 3000))
ALWAYS_RUNNING_SERVICES = [
    CONFIGURATION_HOST,
    DATABASE_HOST,
    NOTIFIER_HOST,
    FILEOBSERVER_HOST,
    PREFIXTREE_HOST,
]
USER_CONTROLLED_SERVICES = [DETECTION_HOST, MITIGATION_HOST, RIPERISTAP_HOST]

# trigger queries
DROP_TRIGGER_QUERY = "DROP TRIGGER IF EXISTS send_update_event ON public.bgp_updates;"
CREATE_TRIGGER_QUERY = "CREATE TRIGGER send_update_event AFTER INSERT ON bgp_updates FOR EACH ROW EXECUTE PROCEDURE rabbitmq.on_row_change('update-insert');"


# TODO: move to utils
def service_to_ips_and_replicas(base_service_name):
    service_to_ips_and_replicas_set = set([])
    addr_infos = socket.getaddrinfo(base_service_name, REST_PORT)
    for addr_info in addr_infos:
        af, sock_type, proto, canon_name, sa = addr_info
        replica_ip = sa[0]
        replica_host_by_addr = socket.gethostbyaddr(replica_ip)[0]
        replica_name_match = re.match(
            r"^artemis_" + re.escape(base_service_name) + r"_(\d+)\.",
            replica_host_by_addr,
        )
        replica_name = "{}_{}".format(base_service_name, replica_name_match.group(1))
        service_to_ips_and_replicas_set.add((replica_name, replica_ip))
    return service_to_ips_and_replicas_set


def bootstrap_intended_services(wo_db):
    try:
        query = (
            "INSERT INTO intended_process_states (name, running) "
            "VALUES (%s, %s) ON CONFLICT(name) DO NOTHING"
        )
        services_with_status = []
        for service in ALWAYS_RUNNING_SERVICES:
            services_with_status.append((service, True))
        # TODO: move to False initialization after testing and let frontend set this at will
        for service in USER_CONTROLLED_SERVICES:
            services_with_status.append((service, True))
        wo_db.execute_batch(query, services_with_status)
        # if the user does not wish to auto-recover user-controlled processes on startup,
        # initialize with False
        if AUTO_RECOVER_PROCESS_STATE != "true":
            for service in USER_CONTROLLED_SERVICES:
                query = (
                    "UPDATE intended_process_states "
                    "SET running=false "
                    "WHERE name=%s"
                )
                wo_db.execute(query, (service,))
    except Exception:
        log.exception("exception")


def set_current_service_status(wo_db, service, running=False):
    query = (
        "INSERT INTO process_states (name, running) "
        "VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
        "SET running = EXCLUDED.running"
    )
    wo_db.execute(query, (service, running))


def check_and_control_services(ro_db, wo_db):
    intended_status_query = "SELECT name, running FROM intended_process_states"
    intended_status_entries = ro_db.execute(intended_status_query)
    intended_status_dict = {}
    for service, intended_status in intended_status_entries:
        intended_status_dict[service] = intended_status

    stored_status_query = "SELECT name, running FROM process_states"
    stored_status_entries = ro_db.execute(stored_status_query)
    stored_status_dict = {}
    for service, stored_status in stored_status_entries:
        stored_status_dict[service] = stored_status

    detection_examined = False
    for service in intended_status_dict:
        try:
            ips_and_replicas = service_to_ips_and_replicas(service)
        except Exception:
            log.exception("exception")
            continue
        for replica_name, replica_ip in ips_and_replicas:
            try:
                intended_status = intended_status_dict[service]
                r = requests.get("http://{}:{}/health".format(replica_ip, REST_PORT))
                current_status = True if r.json()["status"] == "running" else False
                # check if we need to update stored status
                stored_status = None
                if replica_name in stored_status_dict:
                    stored_status = stored_status_dict[replica_name]
                if current_status != stored_status:
                    set_current_service_status(
                        wo_db, replica_name, running=current_status
                    )
                # ATTENTION: if response status is unconfigured, then the actual intention is False
                intended_status = (
                    False if r.json()["status"] == "unconfigured" else intended_status
                )
                if intended_status == current_status:
                    # statuses match, do nothing
                    pass
                elif intended_status:
                    log.info(
                        "service '{}' data worker should be running but is not".format(
                            replica_name
                        )
                    )
                    r = requests.post(
                        url="http://{}:{}/control".format(replica_ip, REST_PORT),
                        data=json.dumps({"command": "start"}),
                    )
                    response = r.json()
                    if not response["success"]:
                        raise Exception(response["message"])
                    # activate update trigger when detection turns on
                    if service == DETECTION_HOST and not detection_examined:
                        wo_db.execute(
                            "{}{}".format(DROP_TRIGGER_QUERY, CREATE_TRIGGER_QUERY)
                        )
                    log.info(
                        "service '{}': '{}'".format(replica_name, response["message"])
                    )
                else:
                    log.info(
                        "service '{}' data worker should not be running but it is".format(
                            replica_name
                        )
                    )
                    r = requests.post(
                        url="http://{}:{}/control".format(replica_ip, REST_PORT),
                        data=json.dumps({"command": "stop"}),
                    )
                    response = r.json()
                    if not response["success"]:
                        raise Exception(response["message"])
                    # deactivate update trigger when detection turns off
                    if service == DETECTION_HOST:
                        wo_db.execute("{}".format(DROP_TRIGGER_QUERY))
                    log.info(
                        "service '{}': '{}'".format(replica_name, response["message"])
                    )
                if service == DETECTION_HOST:
                    detection_examined = True
            except Exception:
                log.warning(
                    "could not properly check and control service '{}'. Will retry next round".format(
                        replica_name
                    )
                )


if __name__ == "__main__":
    # DB variables
    # TODO: optional: replace these calls with gql instead of DB queries
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

    # reset stored process status table
    wo_db.execute("TRUNCATE process_states")

    # set always running service to true
    bootstrap_intended_services(wo_db)

    # control the processes that are intended to run or not in an endless loop
    while True:
        check_and_control_services(ro_db, wo_db)
        time.sleep(CHECK_INTERVAL)