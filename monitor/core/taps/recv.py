import sys

from kombu import Connection
from kombu import Exchange
from kombu import Queue
from kombu import uuid
from tqdm import tqdm
from utils import RABBITMQ_URI


if len(sys.argv) == 4:
    EXCHANGE_NAME = sys.argv[1]
    ROUTING_KEY = sys.argv[2]
    LIMIT_UPDATES = int(sys.argv[3])
elif len(sys.argv) == 3:
    EXCHANGE_NAME = sys.argv[1]
    ROUTING_KEY = sys.argv[2]
    LIMIT_UPDATES = 65536
else:
    print("usage: python {} exchange_name routing_key update_num")
    sys.exit()

if LIMIT_UPDATES > 65536:
    print("Cannot support more that 65536 updates at the moment")
    sys.exit()


def bind_and_wait(connection, queue):
    queue.declare(channel=connection.default_channel)
    bind_queue = queue.bind(connection.default_channel)
    for i in tqdm(range(LIMIT_UPDATES)):
        while True:
            if bind_queue.get():
                break


def receiver():
    with Connection(RABBITMQ_URI) as connection:
        exchange = Exchange(
            EXCHANGE_NAME,
            channel=connection,
            type="direct",
            durable=False,
            delivery_mode=1,
        )
        exchange.declare()
        queue = Queue(
            "{}".format(uuid()),
            exchange=exchange,
            routing_key=ROUTING_KEY,
            durable=False,
            auto_delete=True,
            max_priority=1,
            consumer_arguments={"x-priority": 1},
            channel=connection.default_channel,
        )
        bind_and_wait(connection, queue)


if __name__ == "__main__":
    try:
        receiver()
    except KeyboardInterrupt:
        pass
