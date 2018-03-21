import os
import signal
import webapp
from core.parser import ConfParser
from core.monitor import Monitor
from core.detection import Detection
from core.syscheck import SysCheck
from webapp.webapp import WebApplication
from protogrpc.grpc_server import GrpcServer
from webapp.shared import app, db


def main():
    # Configuration Parser
    confparser_ = ConfParser()
    confparser_.parse_file()

    if(confparser_.isValid()):
        systemcheck_ = SysCheck()
        if(systemcheck_.isValid()):

            # Instatiate Modules
            monitor_ = Monitor(confparser_)
            detection_ = Detection(db, confparser_)

            # GRPC Server
            grpc_ = GrpcServer(db, monitor_, detection_)
            grpc_.start()

            # Load Modules to Web Application
            app.config['monitor'] = monitor_
            app.config['detector'] = detection_
            # app.config['mitigator'] = mitigation_

            # Web Application
            webapp_ = WebApplication(db)
            webapp_.start()

            input("\n[!] Press ENTER to exit [!]\n\n")

            # Stop all modules and web application
            monitor_.stop()
            detection_.stop()
            grpc_.stop()
            webapp_.stop()
    else:
        print("The config file is wrong.")


if __name__ == '__main__':
    main()
