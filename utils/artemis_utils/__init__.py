import copy
import hashlib
import logging.config
import logging.handlers
import os
import re
import time
from datetime import datetime
from datetime import timedelta
from ipaddress import ip_network as str2ip
from logging.handlers import SMTPHandler
from typing import List
from typing import Tuple
from xmlrpc.client import ServerProxy

import requests
import ujson as json
import yaml
from gql import Client
from gql import gql
from gql.transport.requests import RequestsHTTPTransport
from kombu import serialization

BULK_TIMER = float(os.getenv("BULK_TIMER", 1))
BACKEND_SUPERVISOR_HOST = os.getenv("BACKEND_SUPERVISOR_HOST", "localhost")
BACKEND_SUPERVISOR_PORT = os.getenv("BACKEND_SUPERVISOR_PORT", 9001)
MON_SUPERVISOR_HOST = os.getenv("MON_SUPERVISOR_HOST")
MON_SUPERVISOR_PORT = os.getenv("MON_SUPERVISOR_PORT")
HISTORIC = os.getenv("HISTORIC", "false")
DB_NAME = os.getenv("DB_NAME", "artemis_db")
DB_USER = os.getenv("DB_USER", "artemis_user")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_PASS = os.getenv("DB_PASS", "Art3m1s")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", 6379)
DEFAULT_HIJACK_LOG_FIELDS = json.dumps(
    [
        "prefix",
        "hijack_as",
        "type",
        "time_started",
        "time_last",
        "peers_seen",
        "configured_prefix",
        "timestamp_of_config",
        "asns_inf",
        "time_detected",
        "key",
        "community_annotation",
        "rpki_status",
        "end_tag",
        "outdated_parent",
        "hijack_url",
    ]
)
try:
    HIJACK_LOG_FIELDS = set(
        json.loads(os.getenv("HIJACK_LOG_FIELDS", DEFAULT_HIJACK_LOG_FIELDS))
    )
except Exception:
    HIJACK_LOG_FIELDS = set(DEFAULT_HIJACK_LOG_FIELDS)
ARTEMIS_WEB_HOST = os.getenv("ARTEMIS_WEB_HOST", "artemis.com")
WITHDRAWN_HIJACK_THRESHOLD = int(os.getenv("WITHDRAWN_HIJACK_THRESHOLD", 80))

RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)
BACKEND_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
    BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT
)
if MON_SUPERVISOR_HOST and MON_SUPERVISOR_PORT:
    MON_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
        MON_SUPERVISOR_HOST, MON_SUPERVISOR_PORT
    )
else:
    MON_SUPERVISOR_URI = None
RIPE_ASSET_REGEX = r"^RIPE_WHOIS_AS_SET_(.*)$"
ASN_REGEX = r"^AS(\d+)$"
RPKI_VALIDATOR_ENABLED = os.getenv("RPKI_VALIDATOR_ENABLED", "false")
RPKI_VALIDATOR_HOST = os.getenv("RPKI_VALIDATOR_HOST", "routinator")
RPKI_VALIDATOR_PORT = os.getenv("RPKI_VALIDATOR_PORT", 3323)
TEST_ENV = os.getenv("TEST_ENV", "false")
GRAPHQL_URI = os.getenv("GRAPHQL_URI")
if GRAPHQL_URI is None:
    HASURA_HOST = os.getenv("HASURA_HOST", "graphql")
    HASURA_PORT = os.getenv("HASURA_PORT", 8080)
    GRAPHQL_URI = "http://{HASURA_HOST}:{HASURA_PORT}/v1alpha1/graphql".format(
        HASURA_HOST=HASURA_HOST, HASURA_PORT=HASURA_PORT
    )
HASURA_GRAPHQL_ACCESS_KEY = os.getenv("HASURA_GRAPHQL_ACCESS_KEY", "@rt3m1s.")
GUI_ENABLED = os.getenv("GUI_ENABLED", "true")
AUTO_RECOVER_PROCESS_STATE = os.getenv("AUTO_RECOVER_PROCESS_STATE", "true")

PROCESS_STATES_LOADING_MUTATION = """
    mutation updateProcessStates($name: String, $loading: Boolean) {
        update_view_processes(where: {name: {_like: $name}}, _set: {loading: $loading}) {
        affected_rows
        returning {
          name
          loading
        }
      }
    }
"""


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


class ModulesState:
    def __init__(self):
        self.backend_server = ServerProxy(BACKEND_SUPERVISOR_URI)
        if MON_SUPERVISOR_URI:
            self.mon_server = ServerProxy(MON_SUPERVISOR_URI)
        else:
            self.mon_server = None

    def call(self, module, action):
        try:
            if module == "all":
                if action == "start":
                    for ctx in {self.backend_server, self.mon_server}:
                        if ctx:
                            ctx.supervisor.startAllProcesses()
                elif action == "stop":
                    for ctx in {self.backend_server, self.mon_server}:
                        if ctx:
                            ctx.supervisor.stopAllProcesses()
            else:
                ctx = self.backend_server
                if module == "monitor":
                    ctx = self.mon_server

                if action == "start":
                    modules = self.is_any_up_or_running(module, up=False)
                    for mod in modules:
                        ctx.supervisor.startProcess(mod)

                elif action == "stop":
                    modules = self.is_any_up_or_running(module)
                    for mod in modules:
                        ctx.supervisor.stopProcess(mod)

        except Exception:
            log.exception("exception")

    def is_any_up_or_running(self, module, up=True):
        ctx = self.backend_server
        if module == "monitor":
            ctx = self.mon_server
        if not ctx:
            return False

        try:
            if up:
                return [
                    "{}:{}".format(x["group"], x["name"])
                    for x in ctx.supervisor.getAllProcessInfo()
                    if x["group"] == module and (x["state"] == 20 or x["state"] == 10)
                ]
            return [
                "{}:{}".format(x["group"], x["name"])
                for x in ctx.supervisor.getAllProcessInfo()
                if x["group"] == module and (x["state"] != 20 and x["state"] != 10)
            ]
        except Exception:
            log.exception("exception")
            return False


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
            subelems = element.decode().split("_")
            prefix_peer_hijack_set = "prefix_{}_peer_{}_hijacks".format(
                subelems[0], subelems[1]
            )
            redis_pipeline.srem(prefix_peer_hijack_set, ephemeral_key)
            if redis_instance.scard(prefix_peer_hijack_set) <= 1:
                redis_pipeline.delete(prefix_peer_hijack_set)
        redis_pipeline.delete("hijack_{}_prefixes_peers".format(ephemeral_key))
    redis_pipeline.execute()


def valid_prefix(input_prefix):
    try:
        str2ip(input_prefix)
    except Exception:
        return False
    return True


def calculate_more_specifics(prefix, min_length, max_length):
    for prefix_length in range(min_length, max_length + 1):
        for sub_prefix in prefix.subnets(new_prefix=prefix_length):
            yield str(sub_prefix)


def translate_rfc2622(input_prefix, just_match=False):
    """
    :param input_prefix: (str) input IPv4/IPv6 prefix that
    should be translated according to RFC2622
    :param just_match: (bool) check only if the prefix
    has matched instead of translating
    :return: output_prefixes: (iterator of str) output IPv4/IPv6 prefixes,
    if not just_match, otherwise True or False
    """

    # ^- is the exclusive more specifics operator; it stands for the more
    #    specifics of the address prefix excluding the address prefix
    #    itself.  For example, 128.9.0.0/16^- contains all the more
    #    specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
    reg_exclusive = re.match(r"^(\S*)\^-$", input_prefix)
    if reg_exclusive:
        matched_prefix = reg_exclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen + 1
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # ^+ is the inclusive more specifics operator; it stands for the more
    #    specifics of the address prefix including the address prefix
    #    itself.  For example, 5.0.0.0/8^+ contains all the more specifics
    #    of 5.0.0.0/8 including 5.0.0.0/8.
    reg_inclusive = re.match(r"^(\S*)\^\+$", input_prefix)
    if reg_inclusive:
        matched_prefix = reg_inclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # ^n where n is an integer, stands for all the length n specifics of
    #    the address prefix.  For example, 30.0.0.0/8^16 contains all the
    #    more specifics of 30.0.0.0/8 which are of length 16 such as
    #    30.9.0.0/16.
    reg_n = re.match(r"^(\S*)\^(\d+)$", input_prefix)
    if reg_n:
        matched_prefix = reg_n.group(1)
        length = int(reg_n.group(2))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = length
            max_length = length
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # ^n-m where n and m are integers, stands for all the length n to
    #      length m specifics of the address prefix.  For example,
    #      30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8
    #      which are of length 24 to 32 such as 30.9.9.96/28.
    reg_n_m = re.match(r"^(\S*)\^(\d+)-(\d+)$", input_prefix)
    if reg_n_m:
        matched_prefix = reg_n_m.group(1)
        min_length = int(reg_n_m.group(2))
        max_length = int(reg_n_m.group(3))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return calculate_more_specifics(matched_prefix_ip, min_length, max_length)

    # nothing has matched
    if just_match:
        return False

    return [input_prefix]


def translate_asn_range(asn_range, just_match=False):
    """
    :param <str> asn_range: <start_asn>-<end_asn>
    :param <bool> just_match: check only if the prefix
    has matched instead of translating
    :return: the list of ASNs corresponding to that range
    """
    reg_range = re.match(r"(\d+)\s*-\s*(\d+)", str(asn_range))
    if reg_range:
        start_asn = int(reg_range.group(1))
        end_asn = int(reg_range.group(2))
        if start_asn > end_asn:
            raise ArtemisError("end-asn before start-asn", asn_range)
        if just_match:
            return True
        return list(range(start_asn, end_asn + 1))

    # nothing has matched
    if just_match:
        return False

    return [asn_range]


def translate_as_set(as_set_id, just_match=False):
    """
    :param as_set_id: the ID of the AS-SET as present in the RIPE database (with a prefix in front for disambiguation)
    :param <bool> just_match: check only if the as_set name has matched instead of translating
    :return: the list of ASes that are present in the set
    """
    as_set = ""
    as_set_match = re.match(RIPE_ASSET_REGEX, as_set_id)
    if as_set_match:
        if just_match:
            return True
        try:
            as_set = as_set_match.group(1)
            as_members = set()
            response = requests.get(
                "https://stat.ripe.net/data/historical-whois/data.json?resource=as-set:{}".format(
                    as_set
                ),
                timeout=10,
            )
            json_response = response.json()
            for obj in json_response["data"]["objects"]:
                if obj["type"] == "as-set" and obj["latest"]:
                    for attr in obj["attributes"]:
                        if attr["attribute"] == "members":
                            value = attr["value"]
                            asn_match = re.match(ASN_REGEX, value)
                            if asn_match:
                                asn = int(asn_match.group(1))
                                as_members.add(asn)
                            else:
                                return {
                                    "success": False,
                                    "payload": {},
                                    "error": "invalid-asn-{}-in-as-set-{}".format(
                                        value, as_set
                                    ),
                                }
                else:
                    continue
            if as_members:
                return {
                    "success": True,
                    "payload": {"as_members": sorted(list(as_members))},
                    "error": False,
                }
            return {
                "success": False,
                "payload": {},
                "error": "empty-as-set-{}".format(as_set),
            }
        except Exception:
            return {
                "success": False,
                "payload": {},
                "error": "error-as-set-resolution-{}".format(as_set),
            }
    return False


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


class mformat_validator:

    mformat_fields = [
        "service",
        "type",
        "prefix",
        "path",
        "communities",
        "timestamp",
        "peer_asn",
    ]
    type_values = {"A", "W"}
    community_keys = {"asn", "value"}

    optional_fields_init = {"communities": []}

    def validate(self, msg):
        self.msg = msg
        if not self.valid_dict():
            return False

        self.add_optional_fields()

        for func in self.valid_generator():
            if not func():
                return False

        return True

    def valid_dict(self):
        if not isinstance(self.msg, dict):
            return False
        return True

    def add_optional_fields(self):
        for field in self.optional_fields_init:
            if field not in self.msg:
                self.msg[field] = self.optional_fields_init[field]

    def valid_fields(self):
        if any(field not in self.msg for field in self.mformat_fields):
            return False
        return True

    def valid_prefix(self):
        try:
            str2ip(self.msg["prefix"])
        except BaseException:
            return False
        return True

    def valid_service(self):
        if not isinstance(self.msg["service"], str):
            return False
        return True

    def valid_type(self):
        if self.msg["type"] not in self.type_values:
            return False
        return True

    def valid_path(self):
        if self.msg["type"] == "A" and not isinstance(self.msg["path"], list):
            return False
        return True

    def valid_communities(self):
        if not isinstance(self.msg["communities"], list):
            return False
        for comm in self.msg["communities"]:
            if not isinstance(comm, dict):
                return False
            if self.community_keys - set(comm.keys()):
                return False
        return True

    def valid_timestamp(self):
        if not isinstance(self.msg["timestamp"], float):
            return False
        if HISTORIC == "false" and datetime.utcfromtimestamp(
            self.msg["timestamp"]
        ) < datetime.utcnow() - timedelta(hours=1, minutes=30):
            return False
        return True

    def valid_peer_asn(self):
        if not isinstance(self.msg["peer_asn"], int):
            return False
        return True

    def valid_generator(self):
        yield self.valid_fields
        yield self.valid_prefix
        yield self.valid_service
        yield self.valid_type
        yield self.valid_path
        yield self.valid_communities
        yield self.valid_timestamp
        yield self.valid_peer_asn


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


def hijack_log_field_formatter(hijack_dict):
    logged_hijack_dict = {}
    try:
        fields_to_log = set(hijack_dict.keys()).intersection(HIJACK_LOG_FIELDS)
        for field in fields_to_log:
            logged_hijack_dict[field] = hijack_dict[field]
        # instead of storing in redis, simply add the hijack url upon logging
        if "hijack_url" in HIJACK_LOG_FIELDS and "key" in hijack_dict:
            logged_hijack_dict["hijack_url"] = "https://{}/main/hijack?key={}".format(
                ARTEMIS_WEB_HOST, hijack_dict["key"]
            )
    except Exception:
        log.exception("exception")
        return hijack_dict
    return logged_hijack_dict


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


def signal_loading(module, status=False):
    if GUI_ENABLED != "true":
        return
    try:

        transport = RequestsHTTPTransport(
            url=GRAPHQL_URI,
            use_json=True,
            headers={
                "Content-type": "application/json; charset=utf-8",
                "x-hasura-admin-secret": HASURA_GRAPHQL_ACCESS_KEY,
            },
            verify=False,
        )

        client = Client(
            retries=3, transport=transport, fetch_schema_from_transport=True
        )

        query = gql(PROCESS_STATES_LOADING_MUTATION)

        params = {"name": "{}%".format(module), "loading": status}

        client.execute(query, variable_values=params)

    except Exception:
        log.exception("exception")


def __remove_prepending(seq: List[int]) -> Tuple[List[int], bool]:
    """
    Method to remove prepending ASs from AS path.
    """
    last_add = None
    new_seq = []
    for x in seq:
        if last_add != x:
            last_add = x
            new_seq.append(x)

    is_loopy = False
    if len(set(seq)) != len(new_seq):
        is_loopy = True
    return new_seq, is_loopy


def __clean_loops(seq: List[int]) -> List[int]:
    """
    Method to remove loops from AS path.
    """
    # use inverse direction to clean loops in the path of the traffic
    seq_inv = seq[::-1]
    new_seq_inv = []
    for x in seq_inv:
        if x not in new_seq_inv:
            new_seq_inv.append(x)
        else:
            x_index = new_seq_inv.index(x)
            new_seq_inv = new_seq_inv[: x_index + 1]
    return new_seq_inv[::-1]


def clean_as_path(path: List[int]) -> List[int]:
    """
    Method for loop and prepending removal.
    """
    (clean_path, is_loopy) = __remove_prepending(path)
    if is_loopy:
        clean_path = __clean_loops(clean_path)
    return clean_path
