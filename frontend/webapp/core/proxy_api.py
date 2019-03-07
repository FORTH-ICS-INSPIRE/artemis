import json
import logging

import requests
from flask import Response
from flask import stream_with_context
from webapp.utils import API_URI

log = logging.getLogger("webapp_logger")


def proxy_api_post(action, parameters):
    try:
        total_count = 0
        url_ = API_URI + "/" + action + build_arguments(parameters)
        log.debug("url: {}".format(url_))
        req = requests.get(url=url_, headers={"Prefer": "count=exact"})
        if "Content-Range" in req.headers:
            total_count = int(req.headers["Content-Range"].split("/")[1])
        ret = {}
        ret["results"] = req.json()
        ret["total"] = total_count
        return ret
    except BaseException:
        log.exception("action: {0}, parameters: {1}".format(action, parameters))
    return None


def proxy_api_downloadTable(action, parameters):
    log.debug("{0}{1}".format(parameters, action))
    url_ = API_URI + "/" + action
    if parameters is not None:
        url_ += "?and=" + parameters

    req = requests.get(url=url_, stream=True)
    return Response(
        stream_with_context(req.iter_content(chunk_size=2048)),
        content_type=req.headers["content-type"],
    )


def build_arguments(parameters):
    url_ = "?"
    try:
        params_ = json.loads(parameters)
    except BaseException:
        log.exception("couldn't json load: {}".format(parameters))
    for parameter in params_:
        url_ += parameter + "=" + str(params_[parameter]) + "&"
    return url_[:-1]
