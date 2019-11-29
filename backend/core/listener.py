import os
import sys
import time

import psycopg2
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from supervisor.childutils import listener
from utils import RABBITMQ_URI


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


def handle_pg_amq_message(message):
    message.ack()


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
                dbname=_db_name, user=_user, host=_host, port=_port, password=_password
            )
        except BaseException as e:
            time.sleep(1)
            write_stderr("Db connection exception: {}".format(e))

    return _db_conn


def run():
    db_conn = create_connect_db()
    db_cursor = db_conn.cursor()
    pg_amq_bridge = Exchange("amq.direct", type="direct", durable=True, delivery_mode=1)
    pg_amq_queue = Queue(
        "listener-pg-amq-update",
        exchange=pg_amq_bridge,
        routing_key="update-insert",
        durable=False,
        auto_delete=True,
        max_priority=1,
        consumer_arguments={"x-priority": 1},
    )
    rmq_connection = Connection(RABBITMQ_URI)
    pg_amq_consumer = Consumer(
        rmq_connection,
        on_message=handle_pg_amq_message,
        queues=[pg_amq_queue],
        prefetch_count=100,
    )

    # TODO: check if the following needs to depend on initial intended db state for detection
    pg_amq_consumer.consume()

    while True:
        headers, body = listener.wait(sys.stdin, sys.stdout)
        body = dict([pair.split(":") for pair in body.split(" ")])
        # write_stderr('{} | {}'.format(headers, body))

        if headers["eventname"] in ("PROCESS_STATE_RUNNING", "PROCESS_STATE_STOPPED"):
            process = body["processname"]
            if process != "listener":
                new_state = headers["eventname"] == "PROCESS_STATE_RUNNING"

                # consumer to work when detection is off, and stop when on
                if process == "detection":
                    if new_state:
                        if pg_amq_consumer.consuming_from(pg_amq_queue):
                            pg_amq_consumer.cancel_by_queue(pg_amq_queue)
                    else:
                        if not pg_amq_consumer.consuming_from(pg_amq_queue):
                            pg_amq_consumer.consume()

                while True:
                    try:
                        write_stderr("{} -> {}".format(process, new_state))
                        db_cursor.execute(query, (process, new_state))
                        db_conn.commit()
                        break
                    except (psycopg2.InterfaceError, psycopg2.OperationalError):
                        db_conn = create_connect_db()
                        db_cursor = db_conn.cursor()
                    except Exception:
                        db_conn.rollback()
                        break

        # acknowledge the event
        write_stdout("RESULT 2\nOK")


if __name__ == "__main__":
    run()
