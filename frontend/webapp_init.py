from webapp.utils import get_logger
log = get_logger()
from webapp.core import app
from webapp.core.modules import Modules_state
from webapp.core.db_stats import DB_statistics
from webapp.core.fetch_config import Configuration
import os
import time


app = app
app.config['configuration'] = Configuration()

while app.config['configuration'].get_newest_config() == False:
    time.sleep(1)
    log.info("waiting for postgrest")

app.config['db_stats'] = DB_statistics()

try:
    app.config['VERSION'] = os.getenv("SYSTEM_VERSION")
except BaseException:
    app.config['VERSION'] = "Fail"
    log.debug("failed to get version")

try:
    log.debug("Starting Scheduler..")
    modules = Modules_state()
    modules.call('scheduler', 'start')
    if not modules.is_up_or_running('scheduler'):
        log.error("Couldn't start scheduler.")
        exit(-1)
except BaseException:
    log.exception("exception while starting scheduler")
    exit(-1)

try:
    log.debug("Starting Postgresql_db..")
    modules.call('postgresql_db', 'start')

    if not modules.is_up_or_running('postgresql_db'):
        log.error("Couldn't start postgresql_db.")
        exit(-1)
except BaseException:
    log.exception("exception while starting postgresql_db")
    exit(-1)

try:
    log.debug("Request status of all modules..")
    status_request = Modules_state()
    status_request.call('all', 'status')
    app.config['status'] = status_request.get_response_all()
except BaseException:
    log.exception("exception while retrieving status of modules..")
    exit(-1)


if __name__ == '__main__':
    app.run(
        host=app.config['WEBAPP_HOST'],
        port=app.config['WEBAPP_PORT'],
        use_reloader=False
    )
