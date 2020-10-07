import datetime
import os
import re
import socket
import time
from xmlrpc.client import ServerProxy

import psycopg2
import redis
import ujson as json
from kombu import Connection
from kombu import Exchange
from kombu import Queue
from kombu import serialization
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

serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)

# additional serializer for pg-amqp messages
serialization.register(
    "txtjson", json.dumps, json.loads, content_type="text", content_encoding="utf-8"
)


class AutoignoreTester:
    def __init__(self):
        self.time_now = int(time.time())
        self.initRedis()
        self.initSupervisor()

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

    def initRedis(self):
        redis_ = redis.Redis(
            host=os.getenv("REDIS_HOST", "backend"), port=os.getenv("REDIS_PORT", 6739)
        )
        self.redis = redis_
        while True:
            try:
                if not self.redis.ping():
                    raise BaseException("could not ping redis")
                break
            except Exception:
                print("retrying redis ping in 5 seconds...")
                time.sleep(5)

    def initSupervisor(self):
        BACKEND_SUPERVISOR_HOST = os.getenv("BACKEND_SUPERVISOR_HOST", "backend")
        BACKEND_SUPERVISOR_PORT = os.getenv("BACKEND_SUPERVISOR_PORT", 9001)
        self.supervisor = ServerProxy(
            "http://{}:{}/RPC2".format(BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT)
        )

    def clear(self):
        db_con = self.getDbConnection()
        db_cur = db_con.cursor()
        query = "delete from bgp_updates; delete from hijacks;"
        db_cur.execute(query)
        db_con.commit()
        db_cur.close()
        db_con.close()

        self.redis.flushall()

        self.curr_idx = 0
        self.send_cnt = 0
        self.expected_messages = 0

    @staticmethod
    def redis_key(prefix, hijack_as, _type):
        assert (
            isinstance(prefix, str)
            and isinstance(hijack_as, int)
            and isinstance(_type, str)
        )
        return AutoignoreTester.get_hash([prefix, hijack_as, _type])

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

    def validate_message(self, body, message):
        """
        Callback method for message validation from the queues.
        """
        print(
            '\033[92mTest "{}" - Receiving Batch #{} - Type {} - Remaining {}'.format(
                self.curr_test,
                self.curr_idx + 1,
                message.delivery_info["routing_key"],
                self.expected_messages - 1,
            )
        )
        if isinstance(body, dict):
            event = body
        else:
            event = json.loads(body)

        # distinguish between type of messages
        if message.delivery_info["routing_key"] == "hijack-update":
            expected = self.messages[self.curr_idx]["database_hijack_response"]
            if event["active"]:
                assert self.redis.sismember(
                    "persistent-keys", event["key"]
                ), "Persistent key not found in Redis"
            else:
                assert not self.redis.sismember(
                    "persistent-keys", event["key"]
                ), "Persistent key found in Redis but should have been removed."

        # compare expected message with received one. exit on
        # mismatch.
        if isinstance(expected, list) and expected:
            expected_item = expected.pop(0)
        else:
            expected_item = expected

        for key in set(event.keys()).intersection(expected_item.keys()):
            if "time" in key:
                expected_item[key] += self.time_now

                # use unix timstamp instead of datetime objects
                if message.delivery_info["routing_key"] == "hijack-update":
                    event[key] = datetime.datetime(
                        *map(int, re.findall(r"\d+", event[key]))
                    ).timestamp()

            assert event[key] == expected_item[key] or (
                isinstance(event[key], (list, set))
                and set(event[key]) == set(expected_item[key])
            ), (
                'Test "{}" - Batch #{} - Type {}: Unexpected'
                ' value for key "{}". Received: {}, Expected: {}'.format(
                    self.curr_test,
                    self.curr_idx,
                    message.delivery_info["routing_key"],
                    key,
                    event[key],
                    expected_item[key],
                )
            )

        self.expected_messages -= 1
        if self.expected_messages <= 0:
            self.curr_idx += 1
        message.ack()

    def send_next_message(self, conn):
        """
        Publish next custom BGP update on the bgp-updates exchange.
        """
        with conn.Producer() as producer:
            self.expected_messages = 0
            for key in self.messages[self.curr_idx]:
                if key != "send":
                    if isinstance(self.messages[self.curr_idx][key], dict):
                        self.expected_messages += 1
                    else:
                        self.expected_messages += len(self.messages[self.curr_idx][key])

            # offset to account for "real-time" tests
            for key in self.messages[self.curr_idx]["send"]:
                if "time" in key:
                    self.messages[self.curr_idx]["send"][key] += self.time_now

            producer.publish(
                self.messages[self.curr_idx]["send"],
                exchange=self.update_exchange,
                routing_key="update",
                serializer="ujson",
            )

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
                routing_key="configuration.rpc.request",
                reply_to=callback_queue.name,
                correlation_id=correlation_id,
                retry=True,
                declare=[
                    Queue(
                        "configuration.rpc.request",
                        durable=False,
                        max_priority=4,
                        consumer_arguments={"x-priority": 4},
                    ),
                    callback_queue,
                ],
                priority=4,
                serializer="ujson",
            )

        while True:
            if callback_queue.get():
                break
            time.sleep(0.1)
        print("Config RPC finished")

    def test(self):
        with Connection(RABBITMQ_URI) as connection:
            # exchanges
            self.update_exchange = Exchange(
                "bgp-update", type="direct", durable=False, delivery_mode=1
            )

            self.pg_amq_bridge = Exchange(
                "amq.direct", type="direct", durable=True, delivery_mode=1
            )

            # queues
            self.update_queue = Queue(
                "detection-testing",
                exchange=self.pg_amq_bridge,
                routing_key="update-update",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )

            self.hijack_db_queue = Queue(
                "hijack-db-testing",
                exchange=self.pg_amq_bridge,
                routing_key="hijack-update",
                durable=False,
                auto_delete=True,
                max_priority=1,
                consumer_arguments={"x-priority": 1},
            )

            print("Waiting for pg_amq exchange..")
            AutoignoreTester.waitExchange(
                self.pg_amq_bridge, connection.default_channel
            )
            print("Waiting for update exchange..")
            AutoignoreTester.waitExchange(
                self.update_exchange, connection.default_channel
            )

            # query database for the states of the processes
            db_con = self.getDbConnection()
            db_cur = db_con.cursor()
            query = "SELECT name FROM process_states WHERE running=True"
            running_modules = set()
            # wait until all 6 modules are running
            while len(running_modules) < 6:
                db_cur.execute(query)
                entries = db_cur.fetchall()
                for entry in entries:
                    running_modules.add(entry[0])
                db_con.commit()
                print("[+] Running modules: {}".format(running_modules))
                print(
                    "[+] {}/6 modules are running. Re-executing query...".format(
                        len(running_modules)
                    )
                )
                time.sleep(1)

            AutoignoreTester.config_request_rpc(connection)

            time.sleep(5)

            db_cur.close()
            db_con.close()

            for testfile in os.listdir("testfiles/"):
                self.clear()

                self.curr_test = testfile
                self.messages = {}

                # load test
                with open("testfiles/{}".format(testfile), "r") as f:
                    self.messages = json.load(f)

                send_len = len(self.messages)

                with nested(
                    connection.Consumer(
                        self.hijack_db_queue,
                        callbacks=[self.validate_message],
                        accept=["ujson", "txtjson"],
                    )
                ):
                    send_cnt = 0
                    # send and validate all messages in the messages.json file
                    while send_cnt < send_len:
                        self.curr_idx = send_cnt
                        self.send_next_message(connection)
                        send_cnt += 1
                        # sleep until we receive all expected messages
                        while self.curr_idx != send_cnt:
                            time.sleep(0.1)
                            try:
                                connection.drain_events(timeout=60)
                            except socket.timeout:
                                # avoid infinite loop by timeout
                                assert False, "Consumer timeout"
                        # sleep for at least 20 seconds between messages so that we check that the ignore mechanism
                        # is not triggered by mistake
                        if send_cnt < send_len:
                            print(
                                "[+] Sleeping for 20 seconds to ensure auto-ignore works correctly"
                            )
                            time.sleep(20)

            connection.close()

        print("[+] Sleeping for 5 seconds...")
        time.sleep(5)
        print("[+] Instructing all processes to stop...")
        self.supervisor.supervisor.stopAllProcesses()

        self.waitProcess("autoignore", 0)  # 0 STOPPED
        self.waitProcess("listener", 0)  # 0 STOPPED
        self.waitProcess("clock", 0)  # 0 STOPPED
        self.waitProcess("configuration", 0)  # 0 STOPPED
        self.waitProcess("database", 0)  # 0 STOPPED
        self.waitProcess("observer", 0)  # 0 STOPPED
        self.waitProcess("detection", 0)  # 0 STOPPED
        print(
            "[+] All processes (listener, clock, conf, db, detection, autoignore and observer) are stopped."
        )


if __name__ == "__main__":
    print("[+] Starting")
    autoignore_tester = AutoignoreTester()
    autoignore_tester.test()
    print("[+] Exiting")
