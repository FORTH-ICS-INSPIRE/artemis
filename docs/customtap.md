**UNDER CONSTRUCTION**

# Building a custom tap
Indicative skeleton for a `monitor/core/taps/custom_tap.py`:
```
import argparse
import pytricia
import redis
from kombu import Connection
from kombu import Exchange
from kombu import Producer
from artemis_utils import get_ip_version
from artemis_utils import get_logger
from artemis_utils import key_generator
from artemis_utils import load_json
from artemis_utils import mformat_validator
from artemis_utils import normalize_msg_path
from artemis_utils import ping_redis
from artemis_utils import RABBITMQ_URI
from artemis_utils import REDIS_HOST
from artemis_utils import REDIS_PORT

...
log = get_logger()
redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60
...

def parse_custom_tap(connection, prefixes_file):
    exchange = Exchange("bgp-update", channel=connection, type="direct", durable=False)
    exchange.declare()

    prefixes = load_json(prefixes_file)
    assert prefixes is not None
    prefix_tree = {"v4": pytricia.PyTricia(32), "v6": pytricia.PyTricia(128)}
    for prefix in prefixes:
        ip_version = get_ip_version(prefix)
        prefix_tree[ip_version].insert(prefix, "")

    validator = mformat_validator()
    with Producer(connection) as producer:
       ...
       for data in custom_stream:
           try:
               # write own parser to translated the incoming BGP update to a Python-compatible dict format
               parsed_dict_format = parse(data)
               # the following fields are mandatory
               msg = {
                   "type": parsed_dict_format["type"],
                   "communities": parsed_dict_format.get("communities", []),
                   "timestamp": float(parsed_dict_format["timestamp"]),
                   "path": parsed_dict_format.get("path", []),
                   "service": "custom_tap...",
                   "prefix": parsed_dict_format["prefix"],
                   "peer_asn": int(parsed_dict_format["peer_asn"]),
               }
               # ignore the message if related to irrelevant prefix
               ip_version = get_ip_version(msg["prefix"])
               if prefix not in prefix_tree[ip_version]:
                   continue
               redis.set(
                   "custom_tap_seen_bgp_update",
                   "1",
                   ex=int(
                       os.getenv(
                           "MON_TIMEOUT_LAST_BGP_UPDATE",
                           DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                       )
                   ),
               )
               if validator.validate(msg):
                   key_generator(msg)
                   log.debug(msg)
                   producer.publish(
                       msg,
                       exchange=exchange,
                       routing_key="update",
                       serializer="json",
               )
               else:
                   log.warning(
                       "Invalid format message: {}".format(msg)
                   )

...

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="My Custom Monitor/Tap")
    parser.add_argument(
        "-p",
        "--prefixes",
        type=str,
        dest="prefixes_file",
        default=None,
        help="Prefix(es) to be monitored (json file with prefix list)",
    )

    args = parser.parse_args()
    ping_redis(redis)

    try:
        with Connection(RABBITMQ_URI) as connection:
            parse_custom_tap(connection, args.prefixes_file)
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
```

# Adding the tap to the available monitor taps
You need to edit `monitor/core/monitor.py` as follows:

[Redis key timeout channels](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/monitor/core/monitor.py#L137):
```
                ...
                self.redis_pubsub_mon_channels = [
                    "__keyspace@0__:ris_seen_bgp_update",
                    "__keyspace@0__:bgpstreamlive_seen_bgp_update",
                    "__keyspace@0__:exabgp_seen_bgp_update",
                    "__keyspace@0__:custom_tap_seen_bgp_update",
                ]
                ...
```
[Initiation of tap instances](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/monitor/core/monitor.py#L216):
```
            ...
            log.info("Initiating configured monitoring instances....")
            self.init_ris_instance()
            self.init_exabgp_instance()
            self.init_bgpstreamhist_instance()
            self.init_bgpstreamlive_instance()
            self.init_custom_tap_instance()
            log.info("All configured monitoring instances initiated.")
            ...
```
Addition of your instance function def:
```
        @exception_handler(log)
        def init_custom_tap_instance(self):
            if "customtap" in self.monitors:
                log.debug(
                    "starting {} for {}".format(
                        self.monitors["customtap"], self.prefix_file
                    )
                )
                p = Popen(
                    [
                        "/usr/local/bin/python3",
                        "taps/custom_tap.py",
                        "--prefixes",
                        self.prefix_file,
                    ],
                    shell=False,
                )
                self.process_ids.append(
                    ("[customtap] {}".format(self.prefix_file), p)
                )
                self.redis.set(
                    "custom_tap_seen_bgp_update",
                    "1",
                    ex=int(
                        os.getenv(
                            "MON_TIMEOUT_LAST_BGP_UPDATE",
                            DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE,
                        )
                    ),
                )
```

# Adding configuration support
You need to edit ``backend/core/configuration.py` as follows:

[Extend supported monitors](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/backend/core/configuration.py#L86):
```
            self.supported_monitors = {
                "riperis",
                "exabgp",
                "bgpstreamhist",
                "bgpstreamlive",
                "betabmp",
                "customtap"
            }
```

# Altering docker-compose to use new changes

TBD
