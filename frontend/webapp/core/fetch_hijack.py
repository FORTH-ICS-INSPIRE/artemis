import requests
from webapp.utils import API_URL_FLASK
import logging

log = logging.getLogger('webapp_logger')

API_PATH = "http://" + API_URL_FLASK


def get_hijack_by_key(hijack_key):
    try:
        log.debug("send request for total get_hijack_by_key")
        url_ = API_PATH + "/view_hijacks?key=eq." + hijack_key
        response = requests.get(url=url_)
        raw_json = response.json()
        log.debug("response: {}".format(raw_json))
        if len(raw_json) > 0:
            return raw_json[0]
        else:
            return None
    except BaseException:
        log.exception("failed to fetch get_hijack_by_key")
    return None
