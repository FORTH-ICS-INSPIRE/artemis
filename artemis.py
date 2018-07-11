import os
import signal
import time
import webapp
from core.parser import ConfParser
from core.monitor import Monitor
from core.detection import Detection
from core.mitigation import Mitigation
from core.syscheck import SysCheck
from webapp.webapp import WebApplication
from protogrpc.grpc_server import GrpcServer
from webapp import app
from webapp.data.models import db

class GracefulKiller:
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True


def main():
    # Configuration Parser
    print('[+] Parsing Configuration..')
    confparser_ = ConfParser()
    confparser_.parse_file()

    if(confparser_.isValid()):
        systemcheck_ = SysCheck()
        if(systemcheck_.isValid()):
            # Instatiate Modules
            monitor_ = Monitor(confparser_)
            detection_ = Detection(confparser_)
            mitigation_ = Mitigation(confparser_)

            # Load Modules to Web Application
            app.config['monitor'] = monitor_
            app.config['detector'] = detection_
            app.config['mitigator'] = mitigation_

            # Web Application
            webapp_ = WebApplication()
            webapp_.start()

            # GRPC Server
            grpc_ = GrpcServer(monitor_, detection_, mitigation_)
            grpc_.start()

            killer = GracefulKiller()
            print('[+] Send SIGTERM signal to end..\n')
            while True:
                time.sleep(1)
                if killer.kill_now:
                    break
            #input("\n[!] Press ENTER to exit [!]\n\n")

            # Stop all modules and web application
            monitor_.stop()
            detection_.stop()
            mitigation_.stop()
            grpc_.stop()
            webapp_.stop()

            db.session.remove()
            print('[+] Bye..!')
    else:
        print('[!] The config file is wrong..')


if __name__ == '__main__':
    main()
