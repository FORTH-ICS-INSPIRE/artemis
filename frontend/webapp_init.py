from webapp.core import app
from webapp.core.rabbitmq import Configuration_request
from webapp.core.modules import Modules_status
from webapp.utils import get_logger
from webapp.core.fetch_config import Configuration
import _thread
import signal
import time


log = get_logger()

class GracefulKiller:
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True


class WebApplication():
    def __init__(self):
        self.app = app
        self.app.config['configuration'] = Configuration()
        self.app.config['configuration'].get_newest_config()
        log.debug(self.app.config['configuration'].get_prefixes_list())

        try:
            log.debug("Starting Scheduler..")
            self.modules = Modules_status()
            self.modules.call('scheduler', 'start')
            if not self.modules.is_up('scheduler'):
                log.error("Couldn't start scheduler.")
        except:
            log.exception("exception while starting scheduler")
            exit(-1)
        
        try:
            log.debug("Starting Postgresql_db..")
            self.modules.call('postgresql_db', 'start')
            
            if not self.modules.is_up('postgresql_db'):
                log.error("Couldn't start postgresql_db.")
        except:
            log.exception("exception while starting postgresql_db")
            exit(-1)

        try:
            log.debug("Request status of all modules..")
            self.status_request = Modules_status()
            self.status_request.call('all', 'status')
            self.app.config['status'] = self.status_request.get_response_all()
        except:
            log.exception("exception while retrieving status of modules..")
            exit(-1)

        self.webapp_ = None

    def start(self):
        log.info("WebApplication Starting..")
        self.app.run(
            threaded=True,
            host=self.app.config['WEBAPP_HOST'],
            port=self.app.config['WEBAPP_PORT'],
            use_reloader=False
        )
        log.info('WebApplication Started..')


if __name__ == '__main__':
    time.sleep(20)
    webapp_ = WebApplication()
    webapp_.start()

    killer = GracefulKiller()
    log.debug('Send SIGTERM signal to end..\n')
    
    while True:
        time.sleep(1)
        if killer.kill_now:
            break