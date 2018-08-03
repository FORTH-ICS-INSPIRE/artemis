import os
import signal
import time
from core.configuration import Configuration
from core.monitor import Monitor
from core.detection import Detection
from protogrpc.grpc_server import GrpcServer
from utils import log


class GracefulKiller:
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self,signum, frame):
        self.kill_now = True


def main():
    # Instatiate Modules
    configuration_ = Configuration()
    configuration_.init_start()

    monitor_ = Monitor()
    monitor_.init_start()

    detection_ = Detection()
    detection_.init_start()

    # GRPC Server
    grpc_ = GrpcServer()
    grpc_.start()

    killer = GracefulKiller()
    log.info('Send SIGTERM signal to end..\n')
    while True:
        time.sleep(1)
        if killer.kill_now:
            break
    #input("\n[!] Press ENTER to exit [!]\n\n")

    # Stop all modules and web application
    configuration_.final_stop()
    monitor_.final_stop()
    detection_.final_stop()
    grpc_.stop()
    log.info('Bye..!')


if __name__ == '__main__':
    main()
