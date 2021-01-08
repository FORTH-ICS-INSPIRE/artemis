# redis aux functions
import time

from . import get_hash
from . import log


def redis_key(prefix, hijack_as, _type):
    assert (
        isinstance(prefix, str)
        and isinstance(hijack_as, int)
        and isinstance(_type, str)
    )
    return get_hash([prefix, hijack_as, _type])


def ping_redis(redis_instance, timeout=5):
    while True:
        try:
            if not redis_instance.ping():
                raise BaseException("could not ping redis")
            break
        except Exception:
            log.error("retrying redis ping in {} seconds...".format(timeout))
            time.sleep(timeout)


def purge_redis_eph_pers_keys(redis_instance, ephemeral_key, persistent_key):
    # to prevent detectors from working in parallel with key deletion
    redis_instance.set("{}token_active".format(ephemeral_key), "1")
    if redis_instance.exists("{}token".format(ephemeral_key)):
        token = redis_instance.blpop("{}token".format(ephemeral_key), timeout=60)
        if not token:
            log.info(
                "Redis cleanup encountered redis token timeout for hijack {}".format(
                    persistent_key
                )
            )
    redis_pipeline = redis_instance.pipeline()
    # purge also tokens since they are not relevant any more
    redis_pipeline.delete("{}token_active".format(ephemeral_key))
    redis_pipeline.delete("{}token".format(ephemeral_key))
    redis_pipeline.delete(ephemeral_key)
    redis_pipeline.srem("persistent-keys", persistent_key)
    redis_pipeline.delete("hij_orig_neighb_{}".format(ephemeral_key))
    if redis_instance.exists("hijack_{}_prefixes_peers".format(ephemeral_key)):
        for element in redis_instance.sscan_iter(
            "hijack_{}_prefixes_peers".format(ephemeral_key)
        ):
            subelems = element.decode("utf-8").split("_")
            prefix_peer_hijack_set = "prefix_{}_peer_{}_hijacks".format(
                subelems[0], subelems[1]
            )
            redis_pipeline.srem(prefix_peer_hijack_set, ephemeral_key)
            if redis_instance.scard(prefix_peer_hijack_set) <= 1:
                redis_pipeline.delete(prefix_peer_hijack_set)
        redis_pipeline.delete("hijack_{}_prefixes_peers".format(ephemeral_key))
    redis_pipeline.execute()


class RedisExpiryChecker:
    """
    Checker for redis expiry events (stops data worker and allows it to restart automatically)
    """

    def __init__(
        self,
        redis=None,
        shared_memory_manager_dict=None,
        monitor=None,
        stop_data_worker_fun=None,
    ):
        self.redis = redis
        self.shared_memory_manager_dict = shared_memory_manager_dict
        self.redis_pubsub = self.redis.pubsub()
        self.redis_pubsub_mon_channel = "__keyspace@0__:{}_seen_bgp_update".format(
            monitor
        )
        self.redis_listener_thread = None
        self.stop_data_worker_fun = stop_data_worker_fun

    def redis_event_handler(self, msg):
        if (
            "pattern" in msg
            and "channel" in msg
            and "data" in msg
            and str(msg["channel"].decode()) == self.redis_pubsub_mon_channel
            and str(msg["data"].decode()) == "expired"
            and self.shared_memory_manager_dict["data_worker_configured"]
            and self.shared_memory_manager_dict["data_worker_running"]
        ):
            stop_msg = self.stop_data_worker_fun(self.shared_memory_manager_dict)
            log.info(stop_msg)

    def run(self):
        try:
            self.redis_pubsub.psubscribe(
                **{self.redis_pubsub_mon_channel: self.redis_event_handler}
            )
            self.redis_listener_thread = self.redis_pubsub.run_in_thread(sleep_time=1)
        except Exception:
            log.exception("Exception")
