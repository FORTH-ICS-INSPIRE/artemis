import datetime
import difflib
import hashlib
import os
import re
import socket
import time

import psycopg2
import redis
import requests
import ujson as json
from kombu import Connection
from kombu import Exchange
from kombu import Queue
from kombu import serialization
from kombu.utils.compat import nested
from psycopg2 import sql

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


def wait_data_worker_dependencies(data_worker_dependencies):
    while True:
        met_deps = set()
        unmet_deps = set()
        for service in data_worker_dependencies:
            try:
                r = requests.get("http://{}:{}/health".format(service, REST_PORT))
                status = True if r.json()["status"] == "running" else False
                if not status:
                    unmet_deps.add(service)
                else:
                    met_deps.add(service)
            except Exception:
                pass
        if len(unmet_deps) == 0:
            print(
                "all needed data workers started: {}".format(data_worker_dependencies)
            )
            break
        else:
            print(
                "'{}' data workers started, waiting for: '{}'".format(
                    met_deps, unmet_deps
                )
            )
        time.sleep(1)


class Tester:
    def __init__(self):
        self.time_now = int(time.time())
        self.initRedis()

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
                    application_name="detection-tester",
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
            host=os.getenv("REDIS_HOST", "redis"), port=os.getenv("REDIS_PORT", 6739)
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
        return Tester.get_hash([prefix, hijack_as, _type])

    @staticmethod
    def get_hash(obj):
        return hashlib.shake_128(json.dumps(obj).encode("utf-8")).hexdigest(16)

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
        if message.delivery_info["routing_key"] == "update-update":
            if "detection_update_response" not in self.messages[self.curr_idx]:
                message.ack()
                return
            expected = self.messages[self.curr_idx]["detection_update_response"]
            assert self.redis.exists(event["key"]), "Monitor key not found in Redis"
            if "peer_asn" in event:
                assert self.redis.sismember(
                    "peer-asns", event["peer_asn"]
                ), "Monitor/Peer ASN not found in Redis"
        elif message.delivery_info["routing_key"] == "update":
            if "detection_hijack_response" not in self.messages[self.curr_idx]:
                message.ack()
                return
            expected = self.messages[self.curr_idx]["detection_hijack_response"]
            redis_hijack_key = Tester.redis_key(
                event["prefix"], event["hijack_as"], event["type"]
            )
            assert self.redis.exists(redis_hijack_key), "Hijack key not found in Redis"
        elif message.delivery_info["routing_key"] == "hijack-update":
            if "database_hijack_response" not in self.messages[self.curr_idx]:
                message.ack()
                return
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

    def test(self):
        """
        Loads a test file that includes crafted bgp updates as
        input and expected messages as output.
        """
        RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
        RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
        RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
        RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
        RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
            RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
        )

        # exchanges
        self.update_exchange = Exchange(
            "bgp-update", type="direct", durable=False, delivery_mode=1
        )

        self.hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
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

        self.hijack_queue = Queue(
            "hijack-testing",
            exchange=self.hijack_exchange,
            routing_key="update",
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

        with Connection(RABBITMQ_URI) as connection:
            # print("Waiting for pg_amq exchange..")
            # Tester.waitExchange(self.pg_amq_bridge, connection.default_channel)
            # print("Waiting for hijack exchange..")
            # Tester.waitExchange(self.hijack_exchange, connection.default_channel)
            # print("Waiting for update exchange..")
            # Tester.waitExchange(self.update_exchange, connection.default_channel)

            # establish connection to DB
            db_con = self.getDbConnection()
            db_cur = db_con.cursor()

            # wait for dependencies data workers to start
            wait_data_worker_dependencies(DATA_WORKER_DEPENDENCIES)

            while True:
                try:
                    r = requests.get(
                        "http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT)
                    )
                    result = r.json()
                    assert len(result) > 0
                    break
                except Exception:
                    print("exception")
                time.sleep(1)

            time.sleep(1)

            # call all helper functions
            Helper.hijack_resolve(
                db_con, connection, "a", "139.5.46.0/24", "S|0|-|-", 133720
            )
            Helper.hijack_mitigate(db_con, connection, "b", "10.91.236.0/24")
            Helper.hijack_ignore(
                db_con, connection, "c", "139.5.237.0/24", "S|0|-|-", 136334
            )
            Helper.hijack_comment(db_con, connection, "d", "test")
            Helper.hijack_ack(db_con, connection, "e", "true")
            Helper.hijack_multiple_action(
                db_con, connection, ["f", "g"], "hijack_action_acknowledge"
            )
            Helper.hijack_multiple_action(
                db_con, connection, ["f", "g"], "hijack_action_acknowledge_not"
            )
            Helper.hijack_multiple_action(
                db_con, connection, ["f"], "hijack_action_resolve"
            )
            Helper.hijack_multiple_action(
                db_con, connection, ["g"], "hijack_action_ignore"
            )
            # multi-action delete a hijack purged from cache
            Helper.hijack_multiple_action(
                db_con, connection, ["f"], "hijack_action_delete"
            )
            # delete a hijack purged from cache
            Helper.hijack_delete(
                db_con, connection, "g", "139.5.16.0/22", "S|0|-|-", 133676
            )
            # multi-action delete a hijack using cache
            Helper.hijack_multiple_action(
                db_con, connection, ["h"], "hijack_action_delete"
            )
            # delete a hijack using cache
            Helper.hijack_delete(
                db_con, connection, "i", "139.5.24.0/24", "S|0|-|-", 133720
            )
            Helper.hijack_mitigate(db_con, connection, "j", "2001:db8:abcd:12::0/80")
            Helper.load_as_sets(connection)

            time.sleep(1)

            db_cur.close()
            db_con.close()

            for testfile in sorted(os.listdir("testfiles/")):
                self.clear()

                self.curr_test = testfile
                self.messages = {}
                # load test
                with open("testfiles/{}".format(testfile), "r") as f:
                    self.messages = json.load(f)

                send_len = len(self.messages)

                with nested(
                    connection.Consumer(
                        self.hijack_queue,
                        callbacks=[self.validate_message],
                        accept=["ujson"],
                    ),
                    connection.Consumer(
                        self.update_queue,
                        callbacks=[self.validate_message],
                        accept=["ujson", "txtjson"],
                    ),
                    connection.Consumer(
                        self.hijack_db_queue,
                        callbacks=[self.validate_message],
                        accept=["ujson", "txtjson"],
                    ),
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
                                connection.drain_events(timeout=10)
                            except socket.timeout:
                                # avoid infinite loop by timeout
                                assert False, "Consumer timeout"

        with open("configs/config.yaml") as f1, open("configs/config2.yaml") as f2:
            new_data = f2.read()
            old_data = f1.read()

        Helper.change_conf(connection, new_data, old_data, "test")

        time.sleep(5)


class Helper:
    @staticmethod
    def hijack_resolve(db_con, connection, hijack_key, prefix, type_, hijack_as):
        hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )
        with connection.Producer() as producer:
            producer.publish(
                {
                    "key": hijack_key,
                    "prefix": prefix,
                    "type": type_,
                    "hijack_as": hijack_as,
                },
                exchange=hijack_exchange,
                routing_key="resolve",
                priority=2,
                serializer="ujson",
            )
        result = hijack_action_test_result(db_con, hijack_key, "resolved")
        assert (
            result is True
        ), 'Action "hijack_resolve" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def hijack_mitigate(db_con, connection, hijack_key, prefix):
        mitigation_exchange = Exchange(
            "mitigation", type="direct", durable=False, delivery_mode=1
        )
        with connection.Producer() as producer:
            producer.publish(
                {"key": hijack_key, "prefix": prefix},
                exchange=mitigation_exchange,
                routing_key="mitigate",
                priority=2,
                serializer="ujson",
            )
        result = hijack_action_test_result(db_con, hijack_key, "under_mitigation")
        assert (
            result is True
        ), 'Action "hijack_mitigate" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def hijack_ignore(db_con, connection, hijack_key, prefix, type_, hijack_as):
        hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )
        with connection.Producer() as producer:
            producer.publish(
                {
                    "key": hijack_key,
                    "prefix": prefix,
                    "type": type_,
                    "hijack_as": hijack_as,
                },
                exchange=hijack_exchange,
                routing_key="ignore",
                priority=2,
                serializer="ujson",
            )
        result = hijack_action_test_result(db_con, hijack_key, "ignored")
        assert (
            result is True
        ), 'Action "hijack_ignore" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def hijack_comment(db_con, connection, hijack_key, comment):
        r = requests.post(
            url="http://{}:{}/hijackComment".format(DATABASE_HOST, REST_PORT),
            data=json.dumps({"key": hijack_key, "comment": comment}),
        )
        response = r.json()
        assert response["success"]
        result = hijack_action_test_result(db_con, hijack_key, "comment", comment)
        assert (
            result is True
        ), 'Action "hijack_comment" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def change_conf(connection, new_config, old_config, comment):
        changes = "".join(difflib.unified_diff(new_config, old_config))
        if changes:
            r = requests.post(
                url="http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT),
                data=json.dumps(
                    {
                        "type": "yaml",
                        "content": {"config": new_config, "comment": comment},
                    }
                ),
            )
            response = r.json()
            assert response["success"]

    @staticmethod
    def hijack_ack(db_con, connection, hijack_key, state):
        hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )
        with connection.Producer() as producer:
            producer.publish(
                {"key": hijack_key, "state": state},
                exchange=hijack_exchange,
                routing_key="seen",
                priority=2,
                serializer="ujson",
            )
        assert (
            hijack_action_test_result(db_con, hijack_key, "seen", state) is True
        ), 'Action "hijack_ack" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def hijack_delete(db_con, connection, hijack_key, prefix, type_, hijack_as):
        hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )
        with connection.Producer() as producer:
            producer.publish(
                {
                    "key": hijack_key,
                    "prefix": prefix,
                    "type": type_,
                    "hijack_as": hijack_as,
                },
                exchange=hijack_exchange,
                routing_key="delete",
                priority=2,
                serializer="ujson",
            )
        result = hijack_action_test_result(db_con, hijack_key, "delete")
        assert (
            result is True
        ), 'Action "hijack_delete" for hijack id #{0} failed'.format(hijack_key)

    @staticmethod
    def hijack_multiple_action(db_con, connection, hijack_keys, action):
        r = requests.post(
            url="http://{}:{}/hijackMultiAction".format(DATABASE_HOST, REST_PORT),
            data=json.dumps({"keys": hijack_keys, "action": action}),
        )
        response = r.json()
        assert response[
            "success"
        ], 'Action "{}" for [{}] failed with reason: {}'.format(
            action, hijack_keys, response["message"]
        )

    @staticmethod
    def load_as_sets(connection):
        r = requests.get(
            url="http://{}:{}/loadAsSets".format(CONFIGURATION_HOST, REST_PORT)
        )
        response = r.json()
        if not response["success"]:
            print("online as_set test failed!!!")
            with open("configs/config.yaml") as f1, open("configs/config3.yaml") as f3:
                new_data = f3.read()
                old_data = f1.read()
            Helper.change_conf(
                connection, new_data, old_data, "online_as_set_test_failed"
            )
        else:
            print("online as_set test succeeded!!!")


def hijack_action_test_result(db_con, hijack_key, action, extra=None):
    db_cur = db_con.cursor()
    query = None
    query_arguments = None
    if action == "comment":
        query = sql.SQL("SELECT COUNT(1) FROM hijacks WHERE key=%s and {}=%s;").format(
            sql.Identifier(action)
        )
        query_arguments = (hijack_key, extra)
    elif action == "seen":
        query = sql.SQL("SELECT COUNT(1) FROM hijacks WHERE key=%s and {}=%s;").format(
            sql.Identifier(action)
        )
        query_arguments = (hijack_key, extra)
    elif action == "delete":
        query = sql.SQL("SELECT COUNT(1) FROM hijacks WHERE key=%s;")
        query_arguments = hijack_key
    else:
        query = sql.SQL(
            "SELECT COUNT(1) FROM hijacks WHERE key=%s and {}=true;"
        ).format(sql.Identifier(action))
        query_arguments = hijack_key
    max_tries = 0
    while max_tries < 20:
        db_cur.execute(query, query_arguments)
        res = db_cur.fetchone()
        db_con.commit()
        if (res[0] == 1 and action != "delete") or (res[0] == 0 and action == "delete"):
            return True

        time.sleep(1)
        max_tries += 1

    return False


if __name__ == "__main__":
    obj = Tester()
    obj.test()
