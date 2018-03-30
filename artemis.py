import os
import signal
import webapp
from core.parser import ConfParser
from core.monitor import Monitor
from core.detection import Detection
from core.mitigation import Mitigation
from core.syscheck import SysCheck
from webapp.webapp import WebApplication
from protogrpc.grpc_server import GrpcServer
from webapp.shared import app, db, db_session


def main():
    # Configuration Parser
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

            input("\n[!] Press ENTER to exit [!]\n\n")

            # Stop all modules and web application
            monitor_.stop()
            detection_.stop()
            mitigation_.stop()
            grpc_.stop()
            webapp_.stop()

            db_session.remove()
    else:
        print("The config file is wrong.")


if __name__ == '__main__':
    main()
