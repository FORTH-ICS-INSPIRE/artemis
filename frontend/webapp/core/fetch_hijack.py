import logging

import requests
from webapp.utils import API_URI

log = logging.getLogger("webapp_logger")


def check_if_hijack_exists(hijack_key):
    try:
        log.debug("send request for total get_hijack_by_key")
        url_ = API_URI + "/view_hijacks?key=eq." + hijack_key
        response = requests.get(url=url_)
        raw_json = response.json()
        log.debug("response: {}".format(raw_json))
        if raw_json:
            return True
    except BaseException:
        log.exception("failed to fetch get_hijack_by_key")
    return False
