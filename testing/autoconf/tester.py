import glob
import os
import re
import time

import psycopg2
import requests
import ujson as json
from kombu import Connection
from kombu import Exchange
from kombu import serialization


serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)


# global vars
CONFIGURATION_HOST = "configuration"
DATABASE_HOST = "database"
DATA_WORKER_DEPENDENCIES = [
    "configuration",
    "database",
    "detection",
    "fileobserver",
    "prefixtree",
]
REST_PORT = 3000
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)


def wait_data_worker_dependencies(data_worker_dependencies):
    while True:
        all_deps_met = True
        for service in data_worker_dependencies:
            try:
                r = requests.get("http://{}:{}/health".format(service, REST_PORT))
                status = True if r.json()["status"] == "running" else False
                if not status:
                    all_deps_met = False
                    break
            except Exception:
                all_deps_met = False
                break
        if all_deps_met:
            print("needed data workers started: {}".format(data_worker_dependencies))
            break
        print(
            "waiting for needed data workers to start: {}".format(
                data_worker_dependencies
            )
        )
        time.sleep(1)


class AutoconfTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.proceed_to_next_test = True
        self.expected_configuration = None
        self.autoconf_exchange = None

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
                    application_name="autoconf-tester",
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

    def send_next_message(self, conn, msg):
        """
        Publish next custom BGP update via the autoconf RPC.
        """

        with conn.Producer() as producer:
            print("[+] Sending message '{}'".format(msg))
            producer.publish(
                msg,
                exchange=self.autoconf_exchange,
                routing_key="update",
                retry=True,
                priority=4,
                serializer="ujson",
            )
            print("[+] Sent message '{}'".format(msg))
            print("Sleeping for 5 seconds before polling configuration...")
            time.sleep(5)
            r = requests.get(
                "http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT)
            )
            result = r.json()
            self.check_config(result)
            print("Configuration is up-to-date! Continuing...")

    def check_config(self, msg):
        """
        Validate new configuration based on autoconf update
        """
        raw = msg
        assert isinstance(raw, dict), "[-] Raw configuration is not a dict"
        for outer_key in self.expected_configuration:
            assert (
                outer_key in raw
            ), "[-] Outer key '{}' not in raw configuration".format(outer_key)
            if isinstance(self.expected_configuration[outer_key], dict):
                for inner_key in self.expected_configuration[outer_key]:
                    assert (
                        inner_key in raw[outer_key]
                    ), "[-] Inner key '{}' of outer key '{}' not in raw configuration ".format(
                        inner_key, outer_key
                    )
                    if isinstance(
                        self.expected_configuration[outer_key][inner_key], list
                    ):
                        assert set(
                            self.expected_configuration[outer_key][inner_key]
                        ) == set(
                            raw[outer_key][inner_key]
                        ), "[-] Values of inner key '{}' of outer key '{}' do not agree: expected '{}', got '{}'".format(
                            inner_key,
                            outer_key,
                            set(self.expected_configuration[outer_key][inner_key]),
                            set(raw[outer_key][inner_key]),
                        )
                    else:
                        assert (
                            self.expected_configuration[outer_key][inner_key]
                            == raw[outer_key][inner_key]
                        ), "[-] Value of inner key '{}' of outer key '{}' does not agree: expected '{}', got '{}'".format(
                            inner_key,
                            outer_key,
                            self.expected_configuration[outer_key][inner_key],
                            raw[outer_key][inner_key],
                        )
            elif isinstance(self.expected_configuration[outer_key], list):
                for i, element in enumerate(self.expected_configuration[outer_key]):
                    for inner_key in element:
                        assert (
                            inner_key in raw[outer_key][i]
                        ), "[-] Inner key '{}' not in raw configuration element '{}' of outer key '{}'".format(
                            inner_key, element, outer_key
                        )
                        if isinstance(element[inner_key], list):
                            assert set(element[inner_key]) == set(
                                raw[outer_key][i][inner_key]
                            ), (
                                "[-] Values of inner key '{}' for element '{}' for outer key '{}' do not agree: "
                                "expected '{}', got '{}'".format(
                                    inner_key,
                                    element,
                                    outer_key,
                                    set(element[inner_key]),
                                    set(raw[outer_key][i][inner_key]),
                                )
                            )
                        else:
                            assert element[inner_key] == raw[outer_key][i][inner_key], (
                                "[-] Value of inner key '{}' for element '{}' for outer key '{}' does not agree: "
                                "expected '{}', got '{}'".format(
                                    inner_key,
                                    element,
                                    outer_key,
                                    element[inner_key],
                                    raw[outer_key][i][inner_key],
                                )
                            )

    def test(self):
        with Connection(RABBITMQ_URI) as connection:
            # exchanges
            self.autoconf_exchange = Exchange(
                "autoconf",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

            # print("[+] Waiting for config exchange..")
            # AutoconfTester.waitExchange(
            #     self.autoconf_exchange, connection.default_channel
            # )

            # wait for dependencies data workers to start
            wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

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
                    autoconf_test_info = json.load(f)
                    message = autoconf_test_info["send"]
                    self.expected_configuration = autoconf_test_info["configuration"]
                    message["timestamp"] = self.time_now + i + 1
                    self.send_next_message(connection, message)


if __name__ == "__main__":
    print("[+] Starting")
    autoconf_tester = AutoconfTester()
    autoconf_tester.test()
    print("[+] Exiting")
