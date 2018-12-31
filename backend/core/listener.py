import sys
from supervisor.childutils import listener
import time
import os
import psycopg2


def write_stdout(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def write_stderr(s):
    sys.stderr.write(s)
    sys.stderr.flush()


query = 'INSERT INTO process_states (name, running) ' \
        'VALUES (%s, %s) ON CONFLICT (name) DO UPDATE ' \
        'SET running = EXCLUDED.running'


def create_connect_db():
    _db_conn = None
    time_sleep_connection_retry = 5
    while _db_conn is None:
        time.sleep(time_sleep_connection_retry)
        try:
            _db_name = os.getenv('DATABASE_NAME', 'artemis_db')
            _user = os.getenv('DATABASE_USER', 'artemis_user')
            _host = os.getenv('DATABASE_HOST', 'postgres')
            _password = os.getenv('DATABASE_PASSWORD', 'Art3m1s')

            _db_conn = psycopg2.connect(
                dbname=_db_name,
                user=_user,
                host=_host,
                password=_password
            )
        except Exception:
            pass

    return _db_conn


def run():
    db_conn = create_connect_db()
    db_cursor = db_conn.cursor()
    while True:
        headers, body = listener.wait(sys.stdin, sys.stdout)
        body = dict([pair.split(":") for pair in body.split(" ")])
        # write_stderr('{} | {}'.format(headers, body))

        if headers['eventname'] in (
                'PROCESS_STATE_RUNNING', 'PROCESS_STATE_STOPPED'):
            process = body['processname']
            if process != 'listener':
                new_state = headers['eventname'] == 'PROCESS_STATE_RUNNING'
                try:
                    write_stderr('{} -> {}'.format(process, new_state))
                    db_cursor.execute(query, (process, new_state))
                    db_conn.commit()
                except Exception:
                    db_conn.rollback()

        # acknowledge the event
        write_stdout("RESULT 2\nOK")


if __name__ == '__main__':
    run()
