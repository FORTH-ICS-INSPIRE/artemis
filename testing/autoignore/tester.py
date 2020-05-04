import glob
import os
import re
import time
from xmlrpc.client import ServerProxy

import psycopg2
import ujson as json
from kombu import Connection
from kombu import serialization

# import socket
# from kombu import Exchange
# from kombu import Queue

# from kombu import uuid
# from kombu.utils.compat import nested

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)
BACKEND_SUPERVISOR_HOST = os.getenv("BACKEND_SUPERVISOR_HOST", "localhost")
BACKEND_SUPERVISOR_PORT = os.getenv("BACKEND_SUPERVISOR_PORT", 9001)
BACKEND_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
    BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT
)

serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)


class AutoignoreTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.proceed_to_next_test = True
        self.expected_configuration = None
        self.supervisor = ServerProxy(
            "http://{}:{}/RPC2".format(BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT)
        )

    def getDbConnection(self):
        """
        Return a connection for the postgres database.
        """
        db_conn = None
        while not db_conn:
            try:
                _db_name = os.getenv("DB_NAME", "artemis_db")
                _user = os.getenv("DB_USER", "artemis_user")
                _host = os.getenv("DB_HOST", "postgres")
                _port = os.getenv("DB_PORT", 5432)
                _password = os.getenv("DB_PASS", "Art3m1s")

                db_conn = psycopg2.connect(
                    application_name="autoignore-tester",
                    dbname=_db_name,
                    user=_user,
                    host=_host,
                    port=_port,
                    password=_password,
                )
            except BaseException:
                time.sleep(1)
        return db_conn

    @staticmethod
    def waitExchange(exchange, channel):
        """
        Wait passively until the exchange is declared.
        """
        while True:
            try:
                exchange.declare(passive=True, channel=channel)
                break
            except Exception:
                time.sleep(1)

    def waitProcess(self, mod, target):
        state = self.supervisor.supervisor.getProcessInfo(mod)["state"]
        while state != target:
            time.sleep(0.5)
            state = self.supervisor.supervisor.getProcessInfo(mod)["state"]

    def test(self):
        with Connection(RABBITMQ_URI) as connection:
            # exchanges

            # queues

            # query database for the states of the processes
            db_con = self.getDbConnection()
            db_cur = db_con.cursor()
            query = "SELECT name FROM process_states WHERE running=True"
            running_modules = set()
            # wait until all 4 modules are running
            while len(running_modules) < 4:
                db_cur.execute(query)
                entries = db_cur.fetchall()
                for entry in entries:
                    running_modules.add(entry[0])
                db_con.commit()
                print("[+] Running modules: {}".format(running_modules))
                print(
                    "[+] {}/4 modules are running. Re-executing query...".format(
                        len(running_modules)
                    )
                )
                time.sleep(1)

            AutoignoreTester.config_request_rpc(connection)

            time.sleep(5)

            db_cur.close()
            db_con.close()

            full_testfiles = glob.glob("testfiles/*.json")
            testfiles_to_id = {}
            for full_testfile in full_testfiles:
                testfile = full_testfile.split("/")[-1]
                id_match = re.match(r"^(\d+)_.*$", testfile)
                if id_match:
                    testfiles_to_id[testfile] = int(id_match.group(1))
            testfiles = sorted(
                list(testfiles_to_id.keys()), key=lambda x: testfiles_to_id[x]
            )
            for i, testfile in enumerate(testfiles):
                print(
                    "[+] Commencing test {}: '{}'".format(
                        i + 1, testfile.split(".json")[0]
                    )
                )
                with open("testfiles/{}".format(testfile), "r") as f:
                    autoignore_test_info = json.load(f)
                    message = autoignore_test_info["send"]
                    message["timestamp"] = self.time_now + i + 1
                    self.send_next_message(connection, message)

            connection.close()

        print("[+] Sleeping for 5 seconds...")
        time.sleep(5)
        print("[+] Instructing all processes to stop...")
        self.supervisor.supervisor.stopAllProcesses()

        self.waitProcess("listener", 0)  # 0 STOPPED
        self.waitProcess("clock", 0)  # 0 STOPPED
        self.waitProcess("configuration", 0)  # 0 STOPPED
        self.waitProcess("database", 0)  # 0 STOPPED
        self.waitProcess("observer", 0)  # 0 STOPPED
        print("[+] All processes (listener, clock, conf, db and observer) are stopped.")


if __name__ == "__main__":
    print("[+] Starting")
    autoignore_tester = AutoignoreTester()
    autoignore_tester.test()
    print("[+] Exiting")
