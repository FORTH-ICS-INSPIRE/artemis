from webapp.core import app
from webapp.utils import log
from webapp.core.rabbitmq import Configuration_request
import _thread
import signal
import time
import tornado.ioloop
import tornado.web

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
        self.app.config['CONFIG'] = self.conf_request.get_conf()
        self.webapp_ = None
        self.flag = False

    def run(self):
        if 'WEBAPP_KEY' in self.app.config and 'WEBAPP_CRT' in self.app.config:
            log.info('SSL: enabled')
            # http://flask.pocoo.org/snippets/111/
            # https://www.digitalocean.com/community/tutorials/openssl-essentials-working-with-ssl-certificates-private-keys-and-csrs
            context = (self.app.config['WEBAPP_CRT'], self.app.config['WEBAPP_KEY'])
            self.app.run(
                host=self.app.config['WEBAPP_HOST'],
                port=self.app.config['WEBAPP_PORT'],
                ssl_context=context,
                use_reloader=False
            )
        else:
            log.info('SSL: disabled')
            self.app.run(
                host=self.app.config['WEBAPP_HOST'],
                port=self.app.config['WEBAPP_PORT'],
                use_reloader=False
            )

    def start(self):
        log.info("WebApplication Starting..")
        if not self.flag:
            self.webapp_ = _thread.start_new_thread(self.run, ())
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
