import signal
import time
import redis

from kombu import Connection
from kombu import Consumer
from kombu import Exchange
from kombu import Queue
from kombu.mixins import ConsumerProducerMixin
from kombu.asynchronous import Timer
from kombu.asynchronous import Entry
from kombu import uuid

from utils.tool import DB
from utils import DB_HOST
from utils import DB_NAME
from utils import DB_PASS
from utils import DB_PORT
from utils import DB_USER
from utils import RABBITMQ_URI
from utils import REDIS_HOST
from utils import REDIS_PORT
from utils import get_logger
from utils import signal_loading
from utils import dict_hash
from utils import redis_key
from utils import ping_redis
from utils import purge_redis_eph_pers_keys

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
            self.connection = connection
            self.rules = None
            # https: // docs.celeryproject.org / projects / kombu / en / stable / reference / kombu.asynchronous.timer.html
            # https://docs.celeryproject.org/projects/kombu/en/stable/_modules/kombu/asynchronous/timer.html#Timer
            self.rule_timer = Timer(max_interval=None, on_error=self.on_timer_error)
            self.rule_timer_entries = {}
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
            self.config_exchange = Exchange(
                "config", type="direct", durable=False, delivery_mode=1
            )

            # QUEUES
            self.config_queue = Queue(
                "autoignore-config-notify",
                exchange=self.config_exchange,
                routing_key="notify",
                durable=False,
                auto_delete=True,
                max_priority=3,
                consumer_arguments={"x-priority": 3},
            )

            # redis db
            self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            ping_redis(self.redis)

        def get_consumers(self, Consumer, channel):
            return [
                Consumer(
                    queues=[self.config_queue],
                    on_message=self.handle_config_notify,
                    prefetch_count=1,
                    accept=["ujson"],
                ),
            ]

        def handle_config_notify(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            signal_loading("autoignore", True)
            try:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.set_rule_timers()
            except Exception:
                log.exception("Exception")
            finally:
                signal_loading("autoignore", False)

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
                routing_key="config-request-queue",
                reply_to=callback_queue.name,
                correlation_id=self.correlation_id,
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
                serializer="ujson",
            )
            with Consumer(
                    self.connection,
                    on_message=self.handle_config_request_reply,
                    queues=[callback_queue],
                    accept=["ujson"],
            ):
                while self.rules is None:
                    self.connection.drain_events()

        def handle_config_request_reply(self, message):
            message.ack()
            log.debug("message: {}\npayload: {}".format(message, message.payload))
            if self.correlation_id == message.properties["correlation_id"]:
                raw = message.payload
                if raw["timestamp"] > self.timestamp:
                    self.timestamp = raw["timestamp"]
                    self.rules = raw.get("rules", [])
                    self.set_rule_timers()

        def set_rule_timers(self):
            conf_rule_hashes = set()
            for rule in self.rules:
                rule_hash = dict_hash(rule)
                conf_rule_hashes.add(rule_hash)
            set_rule_hashes = set(self.rule_timer_entries.keys())
            unconfigured_rule_hashes = conf_rule_hashes - set_rule_hashes
            obsolete_rule_hashes = set_rule_hashes - conf_rule_hashes

            # start not started timers
            for hash in unconfigured_rule_hashes:
                self.rule_timer_entries[hash] = Entry(self.auto_ignore_check_rule, rule, hash)
                self.rule_timer.enter_after(rule["interval"], self.rule_timer_entries[hash])

            # cancel started obsolete timers
            for hash in obsolete_rule_hashes:
                self.rule_timer.cancel(self.rule_timer_entries[hash].tref)

        def on_timer_error(self):
            pass

        def auto_ignore_check_rule(self, rule, hash):
            thres_num_peers_seen = rule["thres_num_peers_seen"]
            thres_num_ases_infected = rule["thres_num_ases_infected"]
            interval = rule["interval"]

            if interval <= 0:
                return

            try:
                # fetch ongoing hijack events
                query = (
                    "SELECT time_started, time_last, num_peers_seen, "
                    "num_asns_inf, key, prefix, hijack_as, type, time_detected, "
                    "configured_prefix, timestamp_of_config, community_annotation, rpki_status "
                    "FROM hijacks WHERE active = true"
                )

                entries = self.ro_db.execute(query)

                # check which of them should be auto-ignored
                time_now = int(time.time())
                for entry in entries:
                    time_last_updated = max(
                        int(entry[1].timestamp()), int(entry[8].timestamp())
                    )
                    num_peers_seen = int(entry[2])
                    num_asns_inf = int(entry[3])
                    hij_key = entry[4]
                    prefix = entry[5]
                    hijack_as = entry[6]
                    hij_type = entry[7]
                    if (
                        (time_now - time_last_updated >= interval)
                        and (num_peers_seen <= num_peers_seen)
                        and (num_asns_inf <= num_asns_inf)
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
            except Exception:
                log.exception("exception")
            finally:
                self.rule_timer.enter_after(rule["interval"], self.rule_timer_entries[hash])