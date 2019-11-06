import os
import sys

from supervisor.childutils import listener
from utils import get_logger
from utils.tool import DB

log = get_logger()


def write_stdout(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def write_stderr(s):
    sys.stderr.write(s)
    sys.stderr.flush()


query = (
    "INSERT INTO process_states (name, running) "
    "VALUES (%s, %s) ON CONFLICT (name) DO UPDATE "
    "SET running = EXCLUDED.running"
)


def run():
    _db_name = os.getenv("DB_NAME", "artemis_db")
    _user = os.getenv("DB_USER", "artemis_user")
    _host = os.getenv("DB_HOST", "postgres")
    _port = os.getenv("DB_PORT", 5432)
    _pass = os.getenv("DB_PASS", "Art3m1s")

    db = DB(
        user=_user,
        password=_pass,
        host=_host,
        port=_port,
        database=_db_name,
        reconnect=True,
    )
    while True:
        headers, body = listener.wait(sys.stdin, sys.stdout)
        body = dict([pair.split(":") for pair in body.split(" ")])
        # write_stderr('{} | {}'.format(headers, body))

        if headers["eventname"] in ("PROCESS_STATE_RUNNING", "PROCESS_STATE_STOPPED"):
            process = body["processname"]
            log.debug(
                "message from {} and event {}".format(process, headers["eventname"])
            )
            if process != "listener":
                new_state = headers["eventname"] == "PROCESS_STATE_RUNNING"
                write_stderr("{} -> {}".format(process, new_state))
                db.execute(query, (process, new_state))

        # acknowledge the event
        write_stdout("RESULT 2\nOK")


if __name__ == "__main__":
    run()
