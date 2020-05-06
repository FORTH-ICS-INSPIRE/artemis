import os
import sys
import time

import psycopg2
from supervisor.childutils import listener


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

drop_trigger_query = "DROP TRIGGER IF EXISTS send_update_event ON public.bgp_updates;"
create_trigger_query = "CREATE TRIGGER send_update_event AFTER INSERT ON bgp_updates FOR EACH ROW EXECUTE PROCEDURE rabbitmq.on_row_change('update-insert');"


def create_connect_db():
    _db_conn = None
    while not _db_conn:
        try:
            _db_name = os.getenv("DB_NAME", "artemis_db")
            _user = os.getenv("DB_USER", "artemis_user")
            _host = os.getenv("DB_HOST", "postgres")
            _port = os.getenv("DB_PORT", 5432)
            _password = os.getenv("DB_PASS", "Art3m1s")

            _db_conn = psycopg2.connect(
                application_name="backend-listener",
                dbname=_db_name,
                user=_user,
                host=_host,
                port=_port,
                password=_password,
            )
        except BaseException as e:
            time.sleep(1)
            write_stderr("Db connection exception: {}".format(e))

    return _db_conn


def run():
    db_conn = create_connect_db()
    db_cursor = db_conn.cursor()
    while True:
        headers, body = listener.wait(sys.stdin, sys.stdout)
        body = dict([pair.split(":") for pair in body.split(" ")])
        # write_stderr('{} | {}'.format(headers, body))

        if headers["eventname"] in ("PROCESS_STATE_RUNNING", "PROCESS_STATE_STOPPED"):
            process = body["processname"]
            if process != "listener":
                new_state = headers["eventname"] == "PROCESS_STATE_RUNNING"
                while True:
                    try:
                        write_stderr("{} -> {}".format(process, new_state))
                        if process.startswith("detection"):
                            if new_state:
                                q = "{}{}{}".format(
                                    drop_trigger_query, create_trigger_query, query
                                )
                            else:
                                q = "{}{}".format(drop_trigger_query, query)
                        else:
                            q = query
                        db_cursor.execute(q, (process, new_state))
                        db_conn.commit()
                        break
                    except (psycopg2.InterfaceError, psycopg2.OperationalError):
                        db_conn = create_connect_db()
                        db_cursor = db_conn.cursor()
                    except BaseException:
                        db_conn.rollback()
                        break

        # acknowledge the event
        write_stdout("RESULT 2\nOK")


if __name__ == "__main__":
    run()
