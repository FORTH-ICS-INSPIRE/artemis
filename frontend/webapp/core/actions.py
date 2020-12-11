import difflib
import logging

import requests
import ujson as json
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from kombu import serialization
from webapp.utils import CONFIGURATION_HOST
from webapp.utils import DATABASE_HOST
from webapp.utils import RABBITMQ_URI
from webapp.utils import REST_PORT

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


def learn_hijack_rule(hijack_key, prefix, type_, hijack_as, action):
    r = requests.post(
        url="http://{}:{}/hijackLearnRule".format(CONFIGURATION_HOST, REST_PORT),
        data=json.dumps(
            {
                "key": hijack_key,
                "prefix": prefix,
                "type": type_,
                "hijack_as": hijack_as,
                "action": action,
            }
        ),
    )
    response = r.json()
    if response["success"]:
        return response["new_yaml_conf"], True
    return response["new_yaml_conf"], False


def comment_hijack(hijack_key, comment):
    r = requests.post(
        url="http://{}:{}/hijackComment".format(DATABASE_HOST, REST_PORT),
        data=json.dumps({"key": hijack_key, "comment": comment}),
    )
    response = r.json()
    if response["success"]:
        return "Comment saved.", True
    return "Error while saving.", False


def submit_new_config(new_config, old_config, comment):
    changes = "".join(difflib.unified_diff(new_config, old_config))
    if changes:
        log.debug("Send 'new config'")
        r = requests.post(
            url="http://{}:{}/config".format(CONFIGURATION_HOST, REST_PORT),
            data=json.dumps(
                {"type": "yaml", "content": {"config": new_config, "comment": comment}}
            ),
        )
        response = r.json()
        if response["success"]:
            log.info("new configuration accepted:\n{}".format(changes))
            return "Configuration file updated.", True
        else:
            log.info("invalid configuration:\n{}".format(new_config))
            return (
                "Invalid configuration file.\n{}".format(response["message"]),
                False,
            )
    return "No changes found on the new configuration.", False


def load_as_sets():
    r = requests.get(
        url="http://{}:{}/loadAsSets".format(CONFIGURATION_HOST, REST_PORT)
    )
    response = r.json()
    if response["success"]:
        return response["payload"]["message"], True
    return response["error"], False


def hijacks_multiple_action(hijack_keys, action):
    r = requests.post(
        url="http://{}:{}/hijackMultiAction".format(DATABASE_HOST, REST_PORT),
        data=json.dumps({"keys": hijack_keys, "action": action}),
    )
    response = r.json()
    return response["success"]
