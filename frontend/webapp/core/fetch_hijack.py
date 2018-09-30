import logging
import requests
import json

log = logging.getLogger('artemis_logger')

PROTOCOL = "http"
CONFIG_URL = "://postgrest:3000/"


def get_hijack_by_key(hijack_key):
    ret_obj = None
    try:
        log.debug("send request for total get_hijack_by_key") 
        url_ = PROTOCOL + CONFIG_URL + "hijacks?key=eq." + hijack_key
        response = requests.get(url=url_)
        raw_json = response.json()
        if len(raw_json) > 0:
            return raw_json[0]
        else:
            return None
        
    except:
        log.exception("failed to fetch get_hijack_by_key")
    return None