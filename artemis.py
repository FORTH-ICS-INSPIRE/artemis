from core.parser import ConfParser
from core.monitor import Monitor
from core.detection import Detection
from core.syscheck import SysCheck
from core.pformat import Pformat
from multiprocessing import Process, Manager, Queue
import os

def main():

    # Read the config file
    confparser_ = ConfParser()

    if(confparser_.isValid()):
        configs = confparser_.get_obj()
        monitors = confparser_.get_monitors()
        # Run system check
        systemcheck_ = SysCheck()
        
        if(systemcheck_.isValid()):

                    
            raw_log_queue = Queue()
            parsed_log_queue = Queue()
            process_ids = list()
            
            print("Starting Monitors...")
            # Start monitors
            monitor_ = Monitor(configs, raw_log_queue, monitors)
            process_ids = monitor_.get_process_ids()

            print("Starting Pformat processing...")
            # Pformat processing  
            pformat_ = Process(target=Pformat, args=(raw_log_queue, parsed_log_queue))
            pformat_.start()
            
            process_ids.append(['Pformat', pformat_])

            print("Starting Detection mechanism...")
            # Start detections
            detection_ = Process(target=Detection, args=(configs, parsed_log_queue))
            detection_.start()

            process_ids.append(['Detection', detection_])

            input("\n\nenter to close\n\n")
            for proc_id in process_ids:
                os.kill(int(proc_id[1]), signal.SIGTERM)
            
    else:
        print("The config file is wrong.")

main()