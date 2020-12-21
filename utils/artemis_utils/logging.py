# aux logging functions
from envvars import ARTEMIS_WEB_HOST
from envvars import HIJACK_LOG_FIELDS

from . import log


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
