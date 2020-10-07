import difflib
import logging

import ujson as json
from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Producer
from kombu import Queue
from kombu import serialization
from kombu import uuid
from webapp.utils import RABBITMQ_URI

log = logging.getLogger("artemis_logger")

serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)


def rmq_hijack_action(obj):
    required_fields = ["payload", "action", "exchange", "routing_key", "priority"]

    if any(field not in obj for field in required_fields):
        log.error(
            "obj passed in function 'rmq_hijack_action' does not include all required fields"
        )
        return

    log.debug(
        "Send '{0}' hijack message with key: {1}".format(
            obj["action"], obj["payload"]["key"]
        )
    )

    exchange = Exchange(obj["exchange"], type="direct", durable=False, delivery_mode=1)

    with Connection(RABBITMQ_URI) as connection:
        with Producer(connection) as producer:
            producer.publish(
                obj["payload"],
                exchange=exchange,
                routing_key=obj["routing_key"],
                priority=2,
                serializer="ujson",
            )


class Learn_hijack_rule:
    def on_response(self, message):
        message.ack()
        if message.properties["correlation_id"] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_key, prefix, type_, hijack_as, action):
        log.debug(
            "Send 'learn_new_rule - {0}' hijack message with key: {1}".format(
                action, hijack_key
            )
        )
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            durable=False,
            exclusive=True,
            auto_delete=True,
            max_priority=4,
            consumer_arguments={"x-priority": 4},
        )
        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                producer.publish(
                    {
                        "key": hijack_key,
                        "prefix": prefix,
                        "type": type_,
                        "hijack_as": hijack_as,
                        "action": action,
                    },
                    exchange="",
                    routing_key="configuration.rpc.hijack-learn-rule",
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    priority=4,
                    serializer="ujson",
                )
            with Consumer(
                connection,
                on_message=self.on_response,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while self.response is None:
                    connection.drain_events()
        if self.response["success"]:
            return self.response["new_yaml_conf"], True
        return self.response["new_yaml_conf"], False


class Comment_hijack:
    def __init__(self):
        self.hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )

    def on_response(self, message):
        message.ack()
        if message.properties["correlation_id"] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_key, comment):
        log.debug("Send 'comment' hijack message with key: {}".format(hijack_key))
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            durable=False,
            exclusive=True,
            auto_delete=True,
            max_priority=4,
            consumer_arguments={"x-priority": 4},
        )
        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                producer.publish(
                    {"key": hijack_key, "comment": comment},
                    exchange="",
                    routing_key="database.rpc.hijack-comment",
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    priority=4,
                    serializer="ujson",
                )
            with Consumer(
                connection,
                on_message=self.on_response,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while self.response is None:
                    connection.drain_events()
        if self.response["status"] == "accepted":
            return "Comment saved.", True
        return "Error while saving.", False


class Submit_new_config:
    def on_response(self, message):
        message.ack()
        if message.properties["correlation_id"] == self.correlation_id:
            self.response = message.payload

    def send(self, new_config, old_config, comment):
        changes = "".join(difflib.unified_diff(new_config, old_config))
        if changes:
            log.debug("Send 'new config'")
            self.response = None
            self.correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )
            with Connection(RABBITMQ_URI) as connection:
                with Producer(connection) as producer:
                    producer.publish(
                        {"config": new_config, "comment": comment},
                        exchange="",
                        routing_key="configuration.rpc.modify",
                        serializer="yaml",
                        retry=True,
                        declare=[callback_queue],
                        reply_to=callback_queue.name,
                        correlation_id=self.correlation_id,
                        priority=4,
                    )
                with Consumer(
                    connection,
                    on_message=self.on_response,
                    queues=[callback_queue],
                    accept=["ujson"],
                ):
                    while self.response is None:
                        connection.drain_events()

            if self.response["status"] == "accepted":
                log.info("new configuration accepted:\n{}".format(changes))
                return "Configuration file updated.", True

            log.info("invalid configuration:\n{}".format(new_config))
            return (
                "Invalid configuration file.\n{}".format(self.response["reason"]),
                False,
            )
        return "No changes found on the new configuration.", False


class Load_as_sets:
    def on_response(self, message):
        message.ack()
        if message.properties["correlation_id"] == self.correlation_id:
            self.response = message.payload

    def send(self):
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            durable=False,
            exclusive=True,
            auto_delete=True,
            max_priority=4,
            consumer_arguments={"x-priority": 4},
        )

        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                producer.publish(
                    {},
                    exchange="",
                    routing_key="configuration.rpc.load-as-sets",
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    priority=4,
                    serializer="ujson",
                )
                with Consumer(
                    connection,
                    on_message=self.on_response,
                    queues=[callback_queue],
                    accept=["ujson"],
                ):
                    while self.response is None:
                        connection.drain_events()

        if self.response["success"]:
            return self.response["payload"]["message"], True
        return self.response["error"], False


class Hijacks_multiple_action:
    def __init__(self):
        self.hijack_exchange = Exchange(
            "hijack-update", type="direct", durable=False, delivery_mode=1
        )

    def on_response(self, message):
        message.ack()
        if message.properties["correlation_id"] == self.correlation_id:
            self.response = message.payload

    def send(self, hijack_keys, action):
        log.debug(
            "Send 'multiple_action - {0}' hijack message with keys: {1}".format(
                action, hijack_keys
            )
        )
        self.response = None
        self.correlation_id = uuid()
        callback_queue = Queue(
            uuid(),
            durable=False,
            exclusive=True,
            auto_delete=True,
            max_priority=2,
            consumer_arguments={"x-priority": 2},
        )
        with Connection(RABBITMQ_URI) as connection:
            with Producer(connection) as producer:
                producer.publish(
                    {"keys": hijack_keys, "action": action},
                    exchange="",
                    routing_key="database.rpc.hijack-multiple-action",
                    retry=True,
                    declare=[callback_queue],
                    reply_to=callback_queue.name,
                    correlation_id=self.correlation_id,
                    priority=4,
                    serializer="ujson",
                )
            with Consumer(
                connection,
                on_message=self.on_response,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while self.response is None:
                    connection.drain_events()
        return self.response["status"] == "accepted"
