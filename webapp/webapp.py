from webapp import app
import _thread


class WebApplication():


    def __init__(self):
        self.app = app
        self.webapp_ = None
        self.flag = False


    def run(self):
        if 'WEBAPP_KEY' in self.app.config and 'WEBAPP_CRT' in self.app.config:
            print('SSL: enabled')
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
            print('SSL: disabled')
            self.app.run(
                host=self.app.config['WEBAPP_HOST'],
                port=self.app.config['WEBAPP_PORT'],
                use_reloader=False
            )


    def start(self):
        if not self.flag:
            self.webapp_ = _thread.start_new_thread(self.run, ())
            self.flag = True
            print('WebApplication Started..')


    def stop(self):
        if self.flag:
            self.flag = False
            print('WebApplication Stopped..')
