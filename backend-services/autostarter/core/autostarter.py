import asyncio
from aiohttp import web, ClientSession
import os

import ujson as json
from artemis_utils import get_logger
from artemis_utils.constants import AUTOIGNORE_HOST
from artemis_utils.constants import BGPSTREAMHISTTAP_HOST
from artemis_utils.constants import BGPSTREAMKAFKATAP_HOST
from artemis_utils.constants import BGPSTREAMLIVETAP_HOST
from artemis_utils.constants import CONFIGURATION_HOST
from artemis_utils.constants import DATABASE_HOST
from artemis_utils.constants import DETECTION_HOST
from artemis_utils.constants import EXABGPTAP_HOST
from artemis_utils.constants import FILEOBSERVER_HOST
from artemis_utils.constants import HEALTH_CHECK_TIMEOUT
from artemis_utils.constants import LOCALHOST
from artemis_utils.constants import MITIGATION_HOST
from artemis_utils.constants import NOTIFIER_HOST
from artemis_utils.constants import PREFIXTREE_HOST
from artemis_utils.constants import RIPERISTAP_HOST
from artemis_utils.asyncdb import DB
from artemis_utils.envvars import AUTO_RECOVER_PROCESS_STATE
from artemis_utils.envvars import DB_HOST
from artemis_utils.envvars import DB_NAME
from artemis_utils.envvars import DB_PASS
from artemis_utils.envvars import DB_PORT
from artemis_utils.envvars import DB_USER
from artemis_utils.envvars import IS_KUBERNETES
from artemis_utils.envvars import REST_PORT
from artemis_utils.envvars import TEST_ENV
from artemis_utils.service import service_to_ips_and_replicas_in_compose
from artemis_utils.service import service_to_ips_and_replicas_in_k8s

# logger
# import logging
# logging.basicConfig(level=logging.DEBUG)
log = get_logger()

# global vars
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))
SERVICE_NAME = "autostarter"
ALWAYS_RUNNING_SERVICES = [
    SERVICE_NAME,
    CONFIGURATION_HOST,
    DATABASE_HOST,
    NOTIFIER_HOST,
    FILEOBSERVER_HOST,
    PREFIXTREE_HOST,
    AUTOIGNORE_HOST,
]
USER_CONTROLLED_SERVICES = [
    DETECTION_HOST,
    MITIGATION_HOST,
    RIPERISTAP_HOST,
    BGPSTREAMLIVETAP_HOST,
    BGPSTREAMKAFKATAP_HOST,
    BGPSTREAMHISTTAP_HOST,
    EXABGPTAP_HOST,
]
DEPRECATED_SERVICES = ["monitor"]

# trigger queries
DROP_TRIGGER_QUERY = "DROP TRIGGER IF EXISTS send_update_event ON public.bgp_updates;"
CREATE_TRIGGER_QUERY = "CREATE TRIGGER send_update_event AFTER INSERT ON bgp_updates FOR EACH ROW EXECUTE PROCEDURE rabbitmq.on_row_change('update-insert');"

# state
state = {
    "status": "stopped",
    "detection_update_trigger": False
}


async def config_get_handler(request):
    return web.json_response({})


async def health_get_handler(request):
    return web.json_response(state)


app = web.Application()
app.add_routes([web.get('/health', health_get_handler)])


class AutostarterWorker:
    """
    Simple worker for autostarter service.
    """

    async def init(self):
        # DB variables
        self.ro_db = DB(
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
        await self.ro_db.init()
        self.wo_db = DB(
            application_name="autostarter-write",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )
        await self.wo_db.init()

        # reset stored process status table
        # (to be re-populated in the following rounds)
        await self.wo_db.execute("TRUNCATE process_states")

        # set always running service to true
        await self.bootstrap_intended_services()

    async def bootstrap_intended_services(self):
        try:
            for service in DEPRECATED_SERVICES:
                query = "DELETE FROM intended_process_states WHERE name=$1"
                await self.wo_db.execute(query, (service,))

            query = (
                "INSERT INTO intended_process_states (name, running) "
                "VALUES ($1, $2) ON CONFLICT(name) DO NOTHING"
            )
            services_with_status = []
            for service in ALWAYS_RUNNING_SERVICES:
                services_with_status.append((service, True))
            for service in USER_CONTROLLED_SERVICES:
                if TEST_ENV == "true":
                    services_with_status.append((service, True))
                else:
                    services_with_status.append((service, False))
            await self.wo_db.execute_batch(query, services_with_status)

            # if the user does not wish to auto-recover user-controlled processes on startup,
            # initialize with False
            if AUTO_RECOVER_PROCESS_STATE != "true":
                for service in USER_CONTROLLED_SERVICES:
                    query = (
                        "UPDATE intended_process_states "
                        "SET running=false "
                        "WHERE name=$1"
                    )
                    await self.wo_db.execute(query, (service,))
        except Exception:
            log.exception("exception")

    async def set_current_service_status(self, service, running=False):
        query = (
            "INSERT INTO process_states (name, running) "
            "VALUES ($1, $2) ON CONFLICT (name) DO UPDATE "
            "SET running = EXCLUDED.running"
        )
        await self.wo_db.execute(query, (service, running,))

    async def check_and_control_services(self):
        intended_status_query = "SELECT name, running FROM intended_process_states"
        intended_status_entries = await self.ro_db.execute(intended_status_query)
        intended_status_dict = {}
        for service, intended_status in intended_status_entries:
            intended_status_dict[service] = intended_status

        stored_status_query = "SELECT name, running FROM process_states"
        stored_status_entries = await self.ro_db.execute(stored_status_query)
        stored_status_dict = {}
        for service, stored_status in stored_status_entries:
            stored_status_dict[service] = stored_status

        ips_and_replicas_per_service = {}
        async with ClientSession() as session:
            for service in intended_status_dict:
                try:
                    if IS_KUBERNETES:
                        ips_and_replicas_per_service[
                            service
                        ] = service_to_ips_and_replicas_in_k8s(service)
                    else:
                        ips_and_replicas_per_service[
                            service
                        ] = service_to_ips_and_replicas_in_compose(SERVICE_NAME, service)
                except Exception:
                    log.exception("exception")
                    continue

                # is same service and no replica found, store current replica (local)
                if (
                        service == SERVICE_NAME
                        and len(ips_and_replicas_per_service[service]) == 0
                ):
                    ips_and_replicas_per_service[service].add(
                        ("{}-1".format(service), LOCALHOST)
                    )

                for replica_name, replica_ip in ips_and_replicas_per_service[service]:
                    try:
                        intended_status = intended_status_dict[service]
                        r = await session.get(
                            "http://{}:{}/health".format(replica_ip, REST_PORT),
                            timeout=HEALTH_CHECK_TIMEOUT,
                        )
                        response = await r.json()
                        current_status = True if response["status"] == "running" else False
                        # check if we need to update stored status
                        stored_status = None
                        if replica_name in stored_status_dict:
                            stored_status = stored_status_dict[replica_name]
                        if current_status != stored_status:
                            await self.set_current_service_status(
                                replica_name, running=current_status
                            )

                        # ATTENTION: if response status is unconfigured, then the actual intention is False
                        intended_status = (
                            False
                            if response["status"] == "unconfigured"
                            else intended_status
                        )
                        if intended_status == current_status:
                            # statuses match, do nothing
                            pass
                        elif intended_status:
                            log.info(
                                "service '{}' worker should be running but is not".format(
                                    replica_name
                                )
                            )

                            # if same service (autostarter), do nothing, it should restart itself
                            if service == SERVICE_NAME:
                                continue

                            r = await session.post(
                                url="http://{}:{}/control".format(replica_ip, REST_PORT),
                                data=json.dumps({"command": "start"}),
                            )
                            response = await r.json()
                            if not response["success"]:
                                raise Exception(response["message"])
                            log.info(
                                "service '{}': '{}'".format(
                                    replica_name, response["message"]
                                )
                            )
                        else:
                            log.info(
                                "service '{}' worker should not be running but it is".format(
                                    replica_name
                                )
                            )
                            r = await session.post(
                                url="http://{}:{}/control".format(replica_ip, REST_PORT),
                                data=json.dumps({"command": "stop"}),
                            )
                            response = await r.json()
                            if not response["success"]:
                                raise Exception(response["message"])
                            log.info(
                                "service '{}': '{}'".format(
                                    replica_name, response["message"]
                                )
                            )
                    except Exception:
                        log.exception(
                            "could not properly check and control service '{}'. Will retry next round".format(
                                replica_name
                            )
                        )

                # in the end, check the special case of detection
                if service == DETECTION_HOST:
                    intended_status = intended_status_dict[service]
                    detection_update_trigger = state["detection_update_trigger"]
                    # activate update trigger when detection is intended to run
                    if intended_status and not detection_update_trigger:
                        await self.wo_db.execute(DROP_TRIGGER_QUERY)
                        await self.wo_db.execute(CREATE_TRIGGER_QUERY)

                        state["detection_update_trigger"] = True

                        log.info("activated pg-amqp trigger for detection")
                    # deactivate update trigger when detection is not intended to run
                    elif not intended_status and detection_update_trigger:
                        await self.wo_db.execute(DROP_TRIGGER_QUERY)

                        state["detection_update_trigger"] = False

                        log.info("deactivated pg-amqp trigger for detection")

        return ips_and_replicas_per_service

    async def run(self):
        state["status"] = "running"
        await self.init()
        # control the processes that are intended to run or not in an endless loop
        ips_and_replicas_per_service_previous = {}
        try:
            while True:
                ips_and_replicas_per_service = await self.check_and_control_services()
                # check if scale-down since in that case we need to delete deprecated process states
                for service in ips_and_replicas_per_service:
                    if service in ips_and_replicas_per_service_previous:
                        replicas_before = set(
                            map(
                                lambda x: x[0],
                                ips_and_replicas_per_service_previous[service],
                            )
                        )
                        replicas_now = set(
                            map(lambda x: x[0], ips_and_replicas_per_service[service])
                        )
                        for scaled_down_instance in replicas_before - replicas_now:
                            try:
                                query = "DELETE FROM process_states WHERE name=$1"
                                await self.wo_db.execute(query, (scaled_down_instance,))
                                log.info(
                                    "removed {} from process states due to down-scaling".format(
                                        scaled_down_instance
                                    )
                                )
                            except Exception:
                                log.exception("exception")
                ips_and_replicas_per_service_previous = ips_and_replicas_per_service
                await asyncio.sleep(CHECK_INTERVAL)
        except Exception:
            log.exception("Autostarter loop got exception")


async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=3000)

    worker = AutostarterWorker()

    asyncio.gather(
        site.start(),
        worker.run()
    )

    # wait forever
    await asyncio.Event().wait()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
