import logging

import requests
import yaml
from webapp.utils import API_URI
from webapp.utils import flatten

log = logging.getLogger("artemis_logger")


class Configuration:
    def __init__(self):
        self.raw_json = None
        self.raw_config = None
        self.config_yaml = None
        self.config_comment = None
        self.time_modified = 0

    def get_newest_config(self):
        try:
            log.debug("send request for newest config: {}".format(self.raw_json))
            url_ = API_URI + "/configs?order=time_modified.desc&limit=1"
            response = requests.get(url=url_)
            self.raw_json = response.json()
            log.debug("received config json: {}".format(self.raw_json))
            # Check if postgrest is up and if a valid config exists
            if not isinstance(self.raw_json, list) or not self.raw_json:
                return False
            if "raw_config" in self.raw_json[0]:
                self.raw_config = self.raw_json[0]["raw_config"]
            if "time_modified" in self.raw_json[0]:
                self.time_modified = self.raw_json[0]["time_modified"]
            if "comment" in self.raw_json[0]:
                self.config_comment = self.raw_json[0]["comment"]

            self.config_yaml = yaml.safe_load(self.raw_config)
        except BaseException:
            log.exception("exception")
            return False
        return True

    def get_prefixes_list(self):
        if not self.config_yaml:
            return []

        prefixes_list = []
        for rule in self.config_yaml["rules"]:
            rule["prefixes"] = flatten(rule["prefixes"])
            for prefix in rule["prefixes"]:
                if prefix not in prefixes_list:
                    prefixes_list.append(prefix)
        return prefixes_list

    def get_rules_list(self):
        return self.config_yaml["rules"]

    def get_raw_response(self):
        return self.raw_json

    def get_yaml(self):
        return self.config_yaml

    def get_raw_config(self):
        return self.raw_config

    def get_config_last_modified(self):
        return self.time_modified

    def get_config_comment(self):
        return self.config_comment


def fetch_all_config_timestamps():
    try:
        log.debug("send request to fetch all config timestamps")
        url_ = API_URI + "/view_configs"
        response = requests.get(url=url_)
        raw_json = response.json()
        if raw_json:
            return raw_json
    except BaseException:
        log.exception("failed to fetch all config timestamps")
    return None
