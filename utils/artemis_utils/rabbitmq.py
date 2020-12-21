from kombu import Exchange
from kombu import Queue
from kombu import uuid


def create_exchange(name, channel=None, _type="direct", declare=False):
    exchange = Exchange(
        name, channel=channel, type=_type, durable=False, delivery_mode=1
    )
    if declare:
        exchange.declare()
    return exchange


def create_queue(module, exchange, routing_key, priority=1, random=False):
    name = "{}.{}.{}".format(module, exchange.name, routing_key)
    if random:
        name += ".{}".format(uuid())
    queue = Queue(
        name,
        exchange=exchange,
        routing_key=routing_key,
        durable=False,
        auto_delete=True,
        max_priority=priority,
        consumer_arguments={"x-priority": priority},
    )
    return queue
