from core.parser import ConfParser
from core.monitor import Monitor
from core.detection import Detection
from core.syscheck import SysCheck
from multiprocessing import Process, Manager, Queue
import os
import signal
from webapp.webapp import WebApplication
from protogrpc.grpc_server import GrpcServer


def main():

    webapp_ = WebApplication()
    webapp_.start()

    confparser_ = ConfParser()
    confparser_.parse_file()

    if(confparser_.isValid()):
        print("Running system check..")
        systemcheck_ = SysCheck()
        if(systemcheck_.isValid()):
            monitor_queue = Queue()

            monitor_ = Monitor(confparser_)
            detection_ = Detection(webapp_.db, confparser_, monitor_queue)

            # GRPC server
            grpc_ = GrpcServer(webapp_.db, monitor_queue)
            grpc_.start(monitor_, detection_)

            input("\n[!] Press ENTER to exit [!]\n\n")

            monitor_.stop()
            detection_.stop()
            grpc_.stop()
            webapp_.stop()
    else:
        print("The config file is wrong.")


if __name__ == '__main__':
    main()
