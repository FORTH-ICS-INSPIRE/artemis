import signal
import time
from threading import Timer

import pytricia
import redis
from artemis_utils import DB_HOST
from artemis_utils import DB_NAME
from artemis_utils import DB_PASS
from artemis_utils import DB_PORT
from artemis_utils import DB_USER
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import ping_redis
from artemis_utils import purge_redis_eph_pers_keys
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import redis_key
from artemis_utils import REDIS_PORT
from artemis_utils import signal_loading
from artemis_utils import translate_rfc2622
from artemis_utils.db_util import DB
from artemis_utils.rabbitmq_util import create_exchange
from artemis_utils.rabbitmq_util import create_queue
from kombu import Connection
from kombu import Consumer
from kombu import Queue
from kombu import uuid
from kombu.mixins import ConsumerProducerMixin

log = get_logger()


class AutoIgnoreChecker:
    def __init__(self):
        self.worker = None
        signal.signal(signal.SIGTERM, self.exit)
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    def run(self):
        """
        Entry function for this service that runs a RabbitMQ worker through Kombu.
        """
        try:
            with Connection(RABBITMQ_URI) as connection:
                self.worker = self.Worker(connection)
                self.worker.run()
        except Exception:
            log.exception("exception")
        finally:
            log.info("stopped")

    def exit(self, signum, frame):
        if self.worker:
            self.worker.ro_db.close()
            self.worker.wo_db.close()
            self.worker.should_stop = True

    class Worker(ConsumerProducerMixin):
        def __init__(self, connection):
            self.module_name = "autoignore"
            self.connection = connection
            self.prefix_tree = None
            self.autoignore_rules = None
            # https: // docs.celeryproject.org / projects / kombu / en / stable / reference / kombu.asynchronous.timer.html
            # https://docs.celeryproject.org/projects/kombu/en/stable/_modules/kombu/asynchronous/timer.html#Timer
            self.rule_timer_threads = {}
            self.timestamp = -1

            # DB variables
            self.ro_db = DB(
                application_name="autoignore-readonly",
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                reconnect=True,
                autocommit=True,
                readonly=True,
            )
            self.wo_db = DB(
                application_name="autoignore-write",
                user=DB_USER,
                password=DB_PASS,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
            )

            # EXCHANGES
            self.config_exchange = create_exchange("config", connection)

            # QUEUES
            self.config_queue = create_queue(
                self.module_name,
                exchange=self.config_exchange,
                routing_key="notify",
                priority=3,
            )

            # redis db
            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            ping_redis(self.redis)

            signal_loading(self.module_name, True)
            self.config_request_rpc()
            signal_loading(self.module_name, False)

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    accept=["ujson"],
                )
            ]

        def handle_config_notify(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            signal_loading(self.module_name, True)
            try:
                config = message.payload
                if config["timestamp"] > self.timestamp:
                    self.timestamp = config["timestamp"]
                    self.autoignore_rules = config.get("autoignore", {})
                    self.build_prefix_tree()
                    self.set_rule_timers()
            except Exception:
                log.exception("Exception")
            finally:
                signal_loading(self.module_name, False)

        def config_request_rpc(self):
            self.correlation_id = uuid()
            callback_queue = Queue(
                uuid(),
                durable=False,
                auto_delete=True,
                max_priority=4,
                consumer_arguments={"x-priority": 4},
            )

            self.producer.publish(
                "",
                exchange="",
                routing_key="configuration.rpc.request",
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
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
            with Consumer(
                self.connection,
                on_message=self.handle_config_request_reply,
                queues=[callback_queue],
                accept=["ujson"],
            ):
                while self.autoignore_rules is None:
                    self.connection.drain_events()

        def handle_config_request_reply(self, message):
            message.ack()
            signal_loading(self.module_name, True)
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                config = message.payload
                if config["timestamp"] > self.timestamp:
                    self.timestamp = config["timestamp"]
                    self.autoignore_rules = config.get("autoignore", [])
                    self.build_prefix_tree()
                    self.set_rule_timers()
            signal_loading(self.module_name, False)

        def build_prefix_tree(self):
            log.info("Starting building autoignore prefix tree...")
            self.prefix_tree = {
                "v4": pytricia.PyTricia(32),
                "v6": pytricia.PyTricia(128),
            }
            raw_prefix_count = 0
            for key in self.autoignore_rules:
                try:
                    rule = self.autoignore_rules[key]
                    for prefix in rule["prefixes"]:
                        for translated_prefix in translate_rfc2622(prefix):
                            ip_version = get_ip_version(translated_prefix)
                            if self.prefix_tree[ip_version].has_key(translated_prefix):
                                node = self.prefix_tree[ip_version][translated_prefix]
                            else:
                                node = {"prefix": translated_prefix, "rule_key": key}
                                self.prefix_tree[ip_version].insert(
                                    translated_prefix, node
                                )
                            raw_prefix_count += 1
                except Exception:
                    log.exception("Exception")
            log.info(
                "{} prefixes integrated in autoignore prefix tree in total".format(
                    raw_prefix_count
                )
            )
            log.info("Finished building autoignore prefix tree.")

        def find_best_prefix_node(self, prefix):
            ip_version = get_ip_version(prefix)
            if prefix in self.prefix_tree[ip_version]:
                return self.prefix_tree[ip_version][prefix]
            return None

        def set_rule_timers(self):
            conf_rule_keys = set()
            for rule_key in self.autoignore_rules:
                conf_rule_keys.add(rule_key)
            current_rule_keys = set(self.rule_timer_threads.keys())

            # cancel started timers
            for key in current_rule_keys:
                try:
                    self.rule_timer_threads[key].cancel()
                    log.debug(
                        "Cancelled timer {} - {}".format(
                            self.rule_timer_threads[key], self.autoignore_rules[key]
                        )
                    )
                except Exception:
                    log.exception(
                        "Exception when stopping timer for rule {}".format(key)
                    )
                finally:
                    del self.rule_timer_threads[key]

            # start configured timers
            for key in conf_rule_keys:
                try:
                    self.rule_timer_threads[key] = Timer(
                        interval=self.autoignore_rules[key]["interval"],
                        function=self.auto_ignore_check_rule,
                        args=[key],
                    )
                    self.rule_timer_threads[key].start()
                    log.debug(
                        "Started timer {} - {}".format(
                            self.rule_timer_threads[key], self.autoignore_rules[key]
                        )
                    )
                except Exception:
                    log.exception(
                        "Exception when starting timer for rule {}".format(key)
                    )

        def auto_ignore_check_rule(self, key):
            rule = self.autoignore_rules.get(key, None)
            if not rule:
                return

            if rule["interval"] <= 0:
                return

            thres_num_peers_seen = rule["thres_num_peers_seen"]
            thres_num_ases_infected = rule["thres_num_ases_infected"]
            interval = rule["interval"]
            log.debug("Checking autoignore rule {}".format(rule))

            try:
                # fetch ongoing hijack events
                query = (
                    "SELECT time_started, time_last, num_peers_seen, "
                    "num_asns_inf, key, prefix, hijack_as, type, time_detected "
                    "FROM hijacks WHERE active = true"
                )

                entries = self.ro_db.execute(query)

                # check which of them should be auto-ignored
                time_now = int(time.time())
                for entry in entries:

                    prefix = entry[5]
                    best_node_match = self.find_best_prefix_node(prefix)
                    if not best_node_match:
                        continue
                    if best_node_match["rule_key"] != key:
                        continue

                    log.debug("Matched prefix {}".format(prefix))

                    time_last_updated = max(
                        int(entry[1].timestamp()), int(entry[8].timestamp())
                    )
                    num_peers_seen = int(entry[2])
                    num_asns_inf = int(entry[3])
                    hij_key = entry[4]
                    hijack_as = entry[6]
                    hij_type = entry[7]
                    if (
                        (time_now - time_last_updated > interval)
                        and (num_peers_seen < thres_num_peers_seen)
                        and (num_asns_inf < thres_num_ases_infected)
                    ):
                        redis_hijack_key = redis_key(prefix, hijack_as, hij_type)
                        # if ongoing, clear redis
                        if self.redis.sismember("persistent-keys", hij_key):
                            purge_redis_eph_pers_keys(
                                self.redis, redis_hijack_key, hij_key
                            )
                        self.wo_db.execute(
                            "UPDATE hijacks SET active=false, dormant=false, under_mitigation=false, seen=false, ignored=true WHERE key=%s;",
                            (hij_key,),
                        )
                        log.debug("Ignored hijack {}".format(entry))
            except Exception:
                log.exception("exception")
            finally:
                self.rule_timer_threads[key] = Timer(
                    interval=self.autoignore_rules[key]["interval"],
                    function=self.auto_ignore_check_rule,
                    args=[key],
                )
                self.rule_timer_threads[key].start()
                log.debug(
                    "Started timer {} - {}".format(
                        self.rule_timer_threads[key], self.autoignore_rules[key]
                    )
                )


def run():
    service = AutoIgnoreChecker()
    service.run()


if __name__ == "__main__":
    run()
