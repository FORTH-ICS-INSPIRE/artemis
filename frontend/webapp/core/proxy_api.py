import logging
import requests
import json
from webapp.utils import API_URL_FLASK

log = logging.getLogger('webapp_logger')

API_PATH = "http://" + API_URL_FLASK


def get_proxy_api(action, parameters):
    try:
        total_count = 0
        url_ = API_PATH + "/" + action + build_arguments(parameters)
        log.debug("url: {}".format(url_))
        response = requests.get(url=url_, headers={"Prefer": "count=exact"})
        if 'Content-Range' in response.headers:
            total_count = int(response.headers['Content-Range'].split('/')[1])
        ret = {}
        ret['results'] = response.json()
        ret['total'] = total_count
        return ret
    except BaseException:
        log.exception(
            "action: {0}, parameters: {1}".format(
                action, parameters))
    return None


def build_arguments(parameters):
    url_ = "?"
    try:
        params_ = json.loads(parameters)
    except BaseException:
        log.exception("couldn't json load: {}".format(parameters))
    for parameter in params_:
        url_ += parameter + "=" + str(params_[parameter]) + "&"
    return url_[:-1]
