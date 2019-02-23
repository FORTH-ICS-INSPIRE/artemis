from kombu import Connection
from kombu import Exchange
from kombu import Producer
from utils import get_logger
from utils import RABBITMQ_URI

log = get_logger()


def run():
    def runner(k):
        msg_ = {
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [8, 3, 2, 1, ord(k)],
            "prefix": "10.0.0.0/8",
            "peer_asn": 8,
        }
        with Connection(RABBITMQ_URI) as connection:
            exchange = Exchange(
                "bgp-update", channel=connection, type="direct", durable=False
            )
            exchange.declare()
            with Producer(connection) as producer:
                for i in range(1000):
                    msg_["timestamp"] = i
                    msg_["key"] = "{}-{}".format(k, i)
                    producer.publish(
                        msg_, exchange=exchange, routing_key="update", serializer="json"
                    )

    import threading

    threads = []
    for i in range(10):
        threads.append(threading.Thread(target=runner, args=(chr(i + 97),)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
