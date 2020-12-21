import copy
import hashlib
import logging.config
import logging.handlers
import os
import time
from logging.handlers import SMTPHandler

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


class TLSSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.starttls()  # for tls add this line
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class SSLSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


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


def dump_json(json_obj, filename):
    with open(filename, "w") as f:
        json.dump(json_obj, f)


def redis_key(prefix, hijack_as, _type):
    assert (
        isinstance(prefix, str)
        and isinstance(hijack_as, int)
        and isinstance(_type, str)
    )
    return get_hash([prefix, hijack_as, _type])


def key_generator(msg):
    msg["key"] = get_hash(
        [
            msg["prefix"],
            msg["path"],
            msg["type"],
            "{0:.6f}".format(msg["timestamp"]),
            msg["peer_asn"],
        ]
    )


def get_hash(obj):
    return hashlib.shake_128(json.dumps(obj).encode("utf-8")).hexdigest(16)


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


def ping_redis(redis_instance, timeout=5):
    while True:
        try:
            if not redis_instance.ping():
                raise BaseException("could not ping redis")
            break
        except Exception:
            log.error("retrying redis ping in {} seconds...".format(timeout))
            time.sleep(timeout)


def decompose_path(path):

    # first do an ultra-fast check if the path is a normal one
    # (simple sequence of ASNs)
    str_path = " ".join(map(str, path))
    if "{" not in str_path and "[" not in str_path and "(" not in str_path:
        return [path]

    # otherwise, check how to decompose
    decomposed_paths = []
    for hop in path:
        hop = str(hop)
        # AS-sets
        if "{" in hop:
            decomposed_hops = hop.lstrip("{").rstrip("}").split(",")
        # AS Confederation Set
        elif "[" in hop:
            decomposed_hops = hop.lstrip("[").rstrip("]").split(",")
        # AS Sequence Set
        elif "(" in hop or ")" in hop:
            decomposed_hops = hop.lstrip("(").rstrip(")").split(",")
        # simple ASN
        else:
            decomposed_hops = [hop]
        new_paths = []
        if not decomposed_paths:
            for dec_hop in decomposed_hops:
                new_paths.append([dec_hop])
        else:
            for prev_path in decomposed_paths:
                if "(" in hop or ")" in hop:
                    new_path = prev_path + decomposed_hops
                    new_paths.append(new_path)
                else:
                    for dec_hop in decomposed_hops:
                        new_path = prev_path + [dec_hop]
                        new_paths.append(new_path)
        decomposed_paths = new_paths
    return decomposed_paths


def normalize_msg_path(msg):
    msgs = []
    path = msg["path"]
    msg["orig_path"] = None
    if isinstance(path, list):
        dec_paths = decompose_path(path)
        if not dec_paths:
            msg["path"] = []
            msgs = [msg]
        elif len(dec_paths) == 1:
            msg["path"] = list(map(int, dec_paths[0]))
            msgs = [msg]
        else:
            for dec_path in dec_paths:
                copied_msg = copy.deepcopy(msg)
                copied_msg["path"] = list(map(int, dec_path))
                copied_msg["orig_path"] = path
                msgs.append(copied_msg)
    else:
        msgs = [msg]

    return msgs


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


def get_rpki_val_result(mgr, asn, network, netmask):
    try:
        result = mgr.validate(asn, network, netmask)
        if result.is_valid:
            return "VD"
        if result.is_invalid:
            if result.as_invalid:
                return "IA"
            if result.length_invalid:
                return "IL"
            return "IU"
        if result.not_found:
            return "NF"
        return "NA"
    except Exception:
        log.exception("exception")
        return "NA"
