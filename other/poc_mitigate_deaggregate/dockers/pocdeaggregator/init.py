import subprocess
import time


PY_BIN = "python"
DEAGG_SCRIPT = "/root/poc_mitigate_deaggregate.py"


print("Sleeping for 20 seconds before initiating test announcement")
time.sleep(20)
cmd_list = [PY_BIN, DEAGG_SCRIPT, "-i", '{"key": "1", "prefix": "192.168.0.0/16"}']
cmd_str = " ".join(cmd_list)
print("\tRunning: {}".format(cmd_str))
subprocess.run(cmd_list)
