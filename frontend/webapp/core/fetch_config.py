from yaml import load as yload
import logging
import requests
import json

log = logging.getLogger('artemis_logger')

PROTOCOL = "http"
CONFIG_URL = "://postgrest:3000/"

class Configuration():

    def __init__(self):
        self.raw_json = None
        self.raw_json_config = None
        self.config_yaml = None

    def get_newest_config(self):
        try:
            url_ = PROTOCOL + CONFIG_URL + "configs?order=id.desc&limit=1"
            response = requests.get(url=url_)
            self.raw_json = response.json()
            log.debug(self.raw_json )
            if 'config_data' in self.raw_json[0]:
                self.raw_json_config = self.raw_json[0]['config_data']
        except:
            log.exception("failed to fetch newest config")

        log.debug(self.raw_json_config)
        data = yload(json.dumps(self.raw_json_config))
        log.debug(data)

    def get_prefixes_list(self):
        if self.config_yaml is None:
            return []
        else:
            return self.config_yaml
        log.debug(self.config_yaml)

    def get_raw(self):
        return self.raw_json

    def get_yaml(self):
        return self.config_yaml

