from webapp.core import app
from webapp.utils import log
from webapp.core.rabbitmq import Configuration_request
from webapp.core.modules import Modules_status
import _thread
import signal
import time

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
        
        self.conf_request = Configuration_request()
        self.conf_request.config_request_rpc()
        self.app.config['configuration'] = self.conf_request.get_conf()

        self.modules = Modules_status()
        log.info("Starting Scheduler..")
        self.modules.call('scheduler', 'start')
        log.info("Starting Postgresql_db..")
        self.modules.call('postgresql_db', 'start')
        
        log.info("Request status of all modules..")
        self.status_request = Modules_status()
        self.status_request.call('all', 'status')
        self.app.config['status'] = self.status_request.get_response_all()
        
        self.webapp_ = None
        self.flag = False

    def run(self):
        if 'WEBAPP_KEY' in self.app.config and 'WEBAPP_CRT' in self.app.config:
            log.info('SSL: enabled')
            # http://flask.pocoo.org/snippets/111/
            # https://www.digitalocean.com/community/tutorials/openssl-essentials-working-with-ssl-certificates-private-keys-and-csrs
            context = (self.app.config['WEBAPP_CRT'], self.app.config['WEBAPP_KEY'])
            self.app.run(
                threaded=True,
                host=self.app.config['WEBAPP_HOST'],
                port=self.app.config['WEBAPP_PORT'],
                ssl_context=context,
                use_reloader=False
            )
        else:
            log.info('SSL: disabled')
            self.app.run(
                threaded=True,
                host=self.app.config['WEBAPP_HOST'],
                port=self.app.config['WEBAPP_PORT'],
                use_reloader=False
            )

    def start(self):
        log.info("WebApplication Starting..")
        if not self.flag:
            self.run()
            self.flag = True
            log.info('WebApplication Started..')

    def stop(self):
        if self.flag:
            self.flag = False
            log.info('WebApplication Stopped..')


if __name__ == '__main__':
    webapp_ = WebApplication()
    webapp_.start()

    killer = GracefulKiller()
    log.info('Send SIGTERM signal to end..\n')
    
    while True:
        time.sleep(1)
        if killer.kill_now:
            break
    
    webapp_.stop()
