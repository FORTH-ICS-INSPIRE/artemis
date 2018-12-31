from webapp.utils import SUPERVISOR_HOST, SUPERVISOR_PORT
from xmlrpc.client import ServerProxy
import time
import logging

log = logging.getLogger('webapp_logger')

intervals = (
    ('W', 604800),  # 60 * 60 * 24 * 7
    ('D', 86400),    # 60 * 60 * 24
    ('H', 3600),    # 60 * 60
    ('M', 60),
    ('S', 1),
)


def display_time(seconds, granularity=2):
    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append('{} {}'.format(int(value), name))
    return ', '.join(result[:granularity])


class Modules_state():

    def __init__(self):
        self.server = ServerProxy(
            'http://{}:{}/RPC2'.format(SUPERVISOR_HOST, SUPERVISOR_PORT))

    def call(self, module, action):
        try:
            if module == 'all':
                if action == 'start':
                    self.server.supervisor.startAllProcesses()
                elif action == 'stop':
                    self.server.supervisor.stopAllProcesses()
            else:
                if action == 'start':
                    modules = self.is_any_up_or_running(module, up=False)
                    for mod in modules:
                        self.server.supervisor.startProcess(mod)
                elif action == 'stop':
                    modules = self.is_any_up_or_running(module)
                    for mod in modules:
                        self.server.supervisor.stopProcess(mod)
        except Exception:
            log.exception('exception')

    def is_up_or_running(self, module):
        try:
            state = self.server.supervisor.getProcessInfo(module)['state']
            while state == 10:
                time.sleep(0.5)
                state = self.server.supervisor.getProcessInfo(module)['state']
            return state == 20
        except Exception:
            log.exception('exception')
            return False

    def is_any_up_or_running(self, module, up=True):
        try:
            if up:
                return ["{}:{}".format(x['group'], x['name']) for x in self.server.supervisor.getAllProcessInfo()
                        if x['group'] == module and (x['state'] == 20 or x['state'] == 10)]
            return ["{}:{}".format(x['group'], x['name']) for x in self.server.supervisor.getAllProcessInfo()
                    if x['group'] == module and (x['state'] != 20 and x['state'] != 10)]
        except Exception:
            log.exception('exception')
            return False

    def get_response_all(self):
        ret_response = {}
        response = self.server.supervisor.getAllProcessInfo()
        for module in response:
            if module['state'] == 20:
                ret_response[module['name']] = {
                    'status': 'up',
                    'uptime': display_time(module['now'] - module['start'])
                }
            else:
                ret_response[module['name']] = {
                    'status': 'down',
                    'uptime': 'N/A'
                }
        return ret_response

    def get_response_formatted_all(self):
        return self.get_response_all()
