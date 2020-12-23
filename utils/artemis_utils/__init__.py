# very basic aux functions for initialization
import hashlib
import logging.config
import logging.handlers
import os

import ujson as json
import yaml
from kombu import serialization


serialization.register(
    "ujson",
    json.dumps,
    json.loads,
    content_type="application/x-ujson",
    content_encoding="utf-8",
)


def get_logger(path="/etc/artemis/logging.yaml"):
    if os.path.exists(path):
        with open(path, "r") as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger("artemis_logger")
        log.info("Loaded configuration from {}".format(path))
    else:
        FORMAT = "%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s"
        logging.basicConfig(format=FORMAT, level=logging.INFO)
        log = logging
        log.info("Loaded default configuration")
    return log


log = get_logger()


def flatten(items, seqtypes=(list, tuple)):
    res = []
    if not isinstance(items, seqtypes):
        return [items]
    for item in items:
        if isinstance(item, seqtypes):
            res += flatten(item)
        else:
            res.append(item)
    return res


def load_json(filename):
    json_obj = None
    try:
        with open(filename, "r") as f:
            json_obj = json.load(f)
    except Exception:
        return None
    return json_obj


def dump_json(json_obj, filename):
    with open(filename, "w") as f:
        json.dump(json_obj, f)


class ArtemisError(Exception):
    def __init__(self, _type, _where):
        self.type = _type
        self.where = _where

        message = "type: {}, at: {}".format(_type, _where)

        # Call the base class constructor with the parameters it needs
        super().__init__(message)


def exception_handler(log):
    def function_wrapper(f):
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                log.exception("exception")
                return True

        return wrapper

    return function_wrapper


def get_hash(obj):
    return hashlib.shake_128(json.dumps(obj).encode("utf-8")).hexdigest(16)


def update_aliased_list(yaml_conf, obj, updated_obj):
    def recurse(y, ref, new_obj):
        if isinstance(y, dict):
            for i, k in [(idx, key) for idx, key in enumerate(y.keys()) if key is ref]:
                y.insert(i, new_obj, y.pop(k))
            for k, v in y.non_merged_items():
                if v is ref:
                    y[k] = new_obj
                else:
                    recurse(v, ref, new_obj)
        elif isinstance(y, list):
            for idx, item in enumerate(y):
                if item is ref:
                    y[idx] = new_obj
                else:
                    recurse(item, ref, new_obj)

    recurse(yaml_conf, obj, updated_obj)


def search_worst_prefix(prefix, pyt_tree):
    if prefix in pyt_tree:
        worst_prefix = pyt_tree.get_key(prefix)
        while pyt_tree.parent(worst_prefix):
            worst_prefix = pyt_tree.parent(worst_prefix)
        return worst_prefix
    return None


def get_ip_version(prefix):
    if ":" in prefix:
        return "v6"
    return "v4"


def chunk_list(bucket, n):
    """Yield successive n-sized chunks from bucket."""
    for i in range(0, len(bucket), n):
        yield bucket[i : i + n]
