from yaml import load as yload
import requests
import json
from webapp.utils import flatten
from webapp.utils import API_URL_FLASK
import logging

log = logging.getLogger('webapp_logger')

API_PATH = 'http://' + API_URL_FLASK


class Configuration():

    def __init__(self):
        self.raw_json = None
        self.raw_json_config = None
        self.raw_config = None
        self.config_yaml = None
        self.config_comment = None
        self.time_modified = 0

    def get_newest_config(self):
        try:
            log.debug(
                'send request for newest config: {}'.format(
                    self.raw_json))
            url_ = API_PATH + '/configs?order=time_modified.desc&limit=1'
            response = requests.get(url=url_)
            self.raw_json = response.json()
            log.debug('received config json: {}'.format(self.raw_json))
            # Check if postgrest is up and if a valid config exists
            if not isinstance(self.raw_json, list) or not self.raw_json:
                return False
            if 'config_data' in self.raw_json[0]:
                self.raw_json_config = self.raw_json[0]['config_data']
            if 'raw_config' in self.raw_json[0]:
                self.raw_config = self.raw_json[0]['raw_config']
            if 'time_modified' in self.raw_json[0]:
                self.time_modified = self.raw_json[0]['time_modified']
            if 'comment' in self.raw_json[0]:
                self.config_comment = self.raw_json[0]['comment']

            self.config_yaml = yload(json.dumps(self.raw_json_config))
        except BaseException:
            log.exception('exception')
            return False
        return True

    def get_prefixes_list(self):
        if not self.config_yaml:
            return []

        prefixes_list = []
        for rule in self.config_yaml['rules']:
            rule['prefixes'] = flatten(rule['prefixes'])
            for prefix in rule['prefixes']:
                if prefix not in prefixes_list:
                    prefixes_list.append(prefix)
        return prefixes_list

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

    def get_raw_json_config(self):
        return self.raw_json_config


def fetch_all_config_timestamps():
    try:
        log.debug('send request to fetch all config timestamps')
        url_ = API_PATH + '/view_configs'
        response = requests.get(url=url_)
        raw_json = response.json()
        if raw_json:
            return raw_json
    except BaseException:
        log.exception('failed to fetch all config timestamps')
    return None
