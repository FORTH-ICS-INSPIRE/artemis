from yaml import load as yload
import logging
import requests
import json
from webapp.utils import API_URL_FLASK

log = logging.getLogger('webapp_logger')

API_PATH = "http://" + API_URL_FLASK


class Configuration():

    def __init__(self):
        self.raw_json = None
        self.raw_json_config = None
        self.raw_config = None
        self.config_yaml = None
        self.time_modified = 0

    def get_newest_config(self):
        try:
            log.debug(
                "send request for newest config: {}".format(
                    self.raw_json))
            url_ = API_PATH + "/configs?order=id.desc&limit=1"
            response = requests.get(url=url_)
            self.raw_json = response.json()
            log.debug("received config json: {}".format(self.raw_json))
            if 'config_data' in self.raw_json[0]:
                self.raw_json_config = self.raw_json[0]['config_data']
            if 'raw_config' in self.raw_json[0]:
                self.raw_config = self.raw_json[0]['raw_config']
            if 'time_modified' in self.raw_json[0]:
                self.time_modified = self.raw_json[0]['time_modified']

        except BaseException:
            log.exception("failed to fetch newest config")

        try:
            self.config_yaml = yload(json.dumps(self.raw_json_config))
        except BaseException:
            log.exception("yaml failed to parse new config")

    def get_prefixes_list(self):
        if self.config_yaml is None:
            return []
        else:
            prefixes_list = []
            if 'prefixes' in self.config_yaml:
                for prefix_group in self.config_yaml['prefixes']:
                    prefixes_list.extend(
                        (self.config_yaml['prefixes'][prefix_group]))
            return prefixes_list

    def get_raw_response(self):
        return self.raw_json

    def get_yaml(self):
        return self.config_yaml

    def get_raw_config(self):
        return self.raw_config

    def get_config_last_modified(self):
        return self.time_modified


def fetch_all_config_timestamps():
    try:
        log.debug("send request to fetch all config timestamps")
        url_ = API_PATH + "/view_configs"
        response = requests.get(url=url_)
        raw_json = response.json()
        if len(raw_json) > 0:
            return raw_json
        else:
            return None
    except BaseException:
        log.exception("failed to fetch all config timestamps")
    return None
