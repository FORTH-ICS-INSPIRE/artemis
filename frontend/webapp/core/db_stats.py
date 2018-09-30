import logging
import requests
import json
import time

log = logging.getLogger('artemis_logger')

PROTOCOL = "http"
CONFIG_URL = "://postgrest:3000/"

class DB_statistics():

    def __init__(self):
        self.total_bgp_updates = 0
        self.total_bgp_unhandled_updates = 0
        self.total_hijacks = 0
        self.total_hijacks_resolved = 0
        self.total_hijacks_under_mitigation = 0
        self.total_hijacks_active = 0
        self.total_hijacks_ignored = 0
        self.url_ = PROTOCOL + CONFIG_URL
        self.timestamp_last_update = 0
        self.refresh_rate_seconds = 3
    
    def get_total_bgp_updates(self):
        try:
            log.debug("send request for total total_bgp_updates") 
            url_ = self.url_ + "bgp_updates?limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_bgp_updates = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_bgp_updates")
   
    def get_total_bgp_unhandled_updates(self):
        try:
            log.debug("send request for total total_bgp_unhandled_updates") 
            url_ = self.url_ + "bgp_updates?handled=eq.false&limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_bgp_unhandled_updates = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_bgp_unhandled_updates")

    def get_total_hijacks(self):
        try:
            log.debug("send request for total total_hijacks") 
            url_ = self.url_ + "hijacks?limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_hijacks = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_hijacks")

    def get_total_hijacks_resolved(self):
        try:
            log.debug("send request for total total_hijacks_resolved") 
            url_ = self.url_ + "hijacks?resolved=eq.true&limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_hijacks_resolved = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_hijacks_resolved")

    def get_total_hijacks_under_mitigation(self):
        try:
            log.debug("send request for total total_hijacks_under_mitigation") 
            url_ = self.url_ + "hijacks?under_mitigation=eq.true&limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_hijacks_under_mitigation = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_hijacks_under_mitigation")

    def get_total_hijacks_active(self):
        try:
            log.debug("send request for total total_hijacks_active") 
            url_ = self.url_ + "hijacks?active=eq.true&limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_hijacks_active = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_hijacks_active")

    def get_total_hijacks_ignored(self):
        try:
            log.debug("send request for total total_hijacks_ignored") 
            url_ = self.url_ + "hijacks?ignored=eq.true&limit=1"
            response = requests.get(url=url_, headers={"Prefer": "count=exact"})
            if 'Content-Range' in response.headers:
                self.total_hijacks_ignored = int(response.headers['Content-Range'].split('/')[1])
        except:
            log.exception("failed to fetch total_hijacks_ignored")

    def get_new_stats(self):
        if((self.timestamp_last_update + self.refresh_rate_seconds) < time.time()):
            self.get_total_bgp_updates()
            self.get_total_bgp_unhandled_updates()
            self.get_total_hijacks()
            self.get_total_hijacks_resolved()
            self.get_total_hijacks_under_mitigation()
            self.get_total_hijacks_active()
            self.get_total_hijacks_ignored()
    
    def get_all_dict(self):
        self.get_new_stats()
        return { 
            'total_bgp_updates': self.total_bgp_updates,
            'total_bgp_unhandled_updates': self.total_bgp_unhandled_updates,
            'total_hijacks': self.total_hijacks,
            'total_hijacks_resolved': self.total_hijacks_resolved,
            'total_hijacks_under_mitigation': self.total_hijacks_under_mitigation,
            'total_hijacks_active': self.total_hijacks_active,
            'total_hijacks_ignored': self.total_hijacks_ignored
         }

    def get_all_formatted_list(self):
        self.get_new_stats()
        return [ 
            ('Total BGP Updates', self.total_bgp_updates),
            ('Unhadled BGP Updates', self.total_bgp_unhandled_updates),
            ('Total Hijacks', self.total_hijacks),
            ('Resolved', self.total_hijacks_resolved),
            ('Under mitigation', self.total_hijacks_under_mitigation),
            ('Ongoing', self.total_hijacks_active),
            ('Ignored', self.total_hijacks_ignored)
         ]













