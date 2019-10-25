import json
import os
import socket
import time
from xmlrpc.client import ServerProxy

import psycopg2
from kombu import Connection
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from kombu.utils.compat import nested


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
TESTING_SEQUENCE = [
    "announcement_origin",
    "announcement_origin_with_neighbors",
    "withdrawal",
]


class AutoconfTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.autoconf_goahead = False
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

    @staticmethod
    def config_request_rpc(conn):
        """
        Initial RPC of this service to request the configuration.
        The RPC is blocked until the configuration service replies back.
        """
        correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            channel=conn.default_channel,
            durable=False,
            auto_delete=True,
            max_priority=4,
            consumer_arguments={"x-priority": 4},
        )

        with conn.Producer() as producer:
            producer.publish(
                "",
                exchange="",
                routing_key="config-request-queue",
                reply_to=callback_queue.name,
                correlation_id=correlation_id,
                retry=True,
                declare=[
                    Queue(
                        "config-request-queue",
                        durable=False,
                        max_priority=4,
                        consumer_arguments={"x-priority": 4},
                    ),
                    callback_queue,
                ],
                priority=4,
            )

        while True:
            if callback_queue.get():
                break
            time.sleep(0.1)
        print("[+] Config RPC finished")

    def send_next_message(self, conn, msg):
        """
        Publish next custom BGP update via the autoconf RPC.
        """
        correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            channel=conn.default_channel,
            durable=False,
            auto_delete=True,
            max_priority=4,
            consumer_arguments={"x-priority": 4},
        )

        with nested(
            conn.Consumer(
                on_message=self.handle_config_notify,
                queues=[self.config_queue],
                no_ack=True,
                accept=["json"],
            ),
            conn.Consumer(
                on_message=self.handle_autoconf_update_goahead_reply,
                queues=[callback_queue],
                no_ack=True,
            ),
        ):
            self.autoconf_goahead = False
            with conn.Producer() as producer:
                print("[+] Sending message '{}'".format(msg))
                producer.publish(
                    msg,
                    exchange="",
                    routing_key="conf-autoconf-update-queue",
                    reply_to=callback_queue.name,
                    correlation_id=correlation_id,
                    retry=True,
                    declare=[
                        Queue(
                            "conf-autoconf-update-queue",
                            durable=False,
                            max_priority=4,
                            consumer_arguments={"x-priority": 4},
                        ),
                        callback_queue,
                    ],
                    priority=4,
                    serializer="json",
                )
                print("[+] Sent message '{}'".format(msg))
                conn.drain_events()
                try:
                    conn.drain_events(timeout=10)
                except socket.timeout:
                    # avoid infinite loop by timeout
                    assert self.autoconf_goahead, "[-] Autoconf consumer timeout"
                print("[+] Concluded autoconf RPC")
                try:
                    conn.drain_events(timeout=10)
                except socket.timeout:
                    # avoid infinite loop by timeout
                    assert (
                        self.config_notify_received
                    ), "[-] Config notify consumer timeout"
                print("[+] Async received config notify")

    def handle_config_notify(self, msg):
        """
        Receive and validate new configuration based on autoconf update
        """
        raw = msg.payload
        assert isinstance(raw, dict), "[-] Raw configuration is not a dict"
        for outer_key in self.expected_configuration:
            assert (
                outer_key in raw
            ), "[-] Outer key '{}' not in raw configuration".format(outer_key)
            if isinstance(self.expected_configuration[outer_key], dict):
                for inner_key in self.expected_configuration[outer_key]:
                    assert (
                        inner_key in raw[outer_key]
                    ), "[-] Inner key '{}' not in raw configuration for outer key '{}'".format(
                        inner_key, outer_key
                    )
                    assert set(
                        self.expected_configuration[outer_key][inner_key]
                    ) == set(
                        raw[outer_key][inner_key]
                    ), "[-] Values of inner key '{}' for outer key '{}' do not agree: expected '{}', got '{}'".format(
                        inner_key,
                        outer_key,
                        self.expected_configuration[outer_key][inner_key],
                        raw[outer_key][inner_key],
                    )
            elif isinstance(self.expected_configuration[outer_key], list):
                for element in self.expected_configuration[outer_key]:
                    for inner_key in element:
                        pass
                        # TODO
        self.config_notify_received = True

    def handle_autoconf_update_goahead_reply(self, msg):
        """
        Receive autoconf RPC reply and proceed
        """
        self.autoconf_goahead = True

    def test(self):
        with Connection(RABBITMQ_URI) as connection:
            # exchanges
            self.config_exchange = Exchange(
                "config",
                channel=connection,
                type="direct",
                durable=False,
                delivery_mode=1,
            )

            # queues
            self.config_queue = Queue(
                "autoconf-config-notify-{}".format(uuid()),
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=2,
                consumer_arguments={"x-priority": 2},
            )
            print("[+] Waiting for config exchange..")
            AutoconfTester.waitExchange(
                self.config_exchange, connection.default_channel
            )

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

            AutoconfTester.config_request_rpc(connection)

            time.sleep(5)

            db_cur.close()
            db_con.close()

            for i, autoconf_test in enumerate(TESTING_SEQUENCE):
                print("[+] Commencing test {}: '{}'".format(i + 1, autoconf_test))
                with open("testfiles/{}.json".format(autoconf_test), "r") as f:
                    autoconf_test_info = json.load(f)
                    message = autoconf_test_info["send"]
                    self.expected_configuration = autoconf_test_info["configuration"]
                    self.config_notify_received = False
                    message["timestamp"] = self.time_now + i + 1
                    self.send_next_message(connection, message)

            connection.close()

        time.sleep(5)
        self.supervisor.supervisor.stopAllProcesses()

        self.waitProcess("listener", 0)  # 0 STOPPED
        self.waitProcess("clock", 0)  # 0 STOPPED
        self.waitProcess("detection", 0)  # 0 STOPPED
        self.waitProcess("mitigation", 0)  # 0 STOPPED
        self.waitProcess("configuration", 0)  # 0 STOPPED
        self.waitProcess("database", 0)  # 0 STOPPED
        self.waitProcess("observer", 0)  # 0 STOPPED


if __name__ == "__main__":
    print("[+] Starting")
    autoconf_tester = AutoconfTester()
    autoconf_tester.test()
    print("[+] Exiting")
