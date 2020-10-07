import hashlib
import json
import sys
import time

EXA_COMMAND_LIST_FILE = "/home/config/exa_mitigation_commands.json"

prev_file_hash = None
while True:
    with open(EXA_COMMAND_LIST_FILE, "r") as f:
        current_file_hash = hashlib.sha512(f.read()).hexdigest()
        if current_file_hash == prev_file_hash:
            time.sleep(1)
            continue
    with open(EXA_COMMAND_LIST_FILE, "r") as f:
        exa_command_list = json.load(f)
        if len(exa_command_list):
            for exa_command in exa_command_list:
                sys.stderr.write(exa_command + "\n")
                sys.stderr.flush()
                sys.stdout.write(exa_command + "\n")
                sys.stdout.flush()
                time.sleep(1)
        prev_file_hash = current_file_hash
        time.sleep(1)
