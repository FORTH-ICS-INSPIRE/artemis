from webapp.utils import SUPERVISOR_HOST, SUPERVISOR_PORT
import logging
from xmlrpc.client import ServerProxy
import time

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
        self.server = ServerProxy('http://{}:{}/RPC2'.format(SUPERVISOR_HOST, SUPERVISOR_PORT))

    def call(self, module, action):
        try:
            if module == 'all':
                if action == 'start':
                    res = self.server.supervisor.startAllProcesses()
                elif action == 'stop':
                    res = self.server.supervisor.stopAllProcesses()
            else:
                state = self.server.supervisor.getProcessInfo(module)['state']
                if action == 'start':
                    if state != 20 and state != 10:
                        res = self.server.supervisor.startProcess(module)
                    else:
                        res = 'Already started'
                elif action == 'stop':
                    if state == 20 or state == 10:
                        res = self.server.supervisor.stopProcess(module)
                    else:
                        res = 'Already stopped'
        except Exception as e:
            log.exception('exception')
            res = str(e)

        return res

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

    def is_any_up_or_running(self, module):
        try:
            return [x['name'] for x in self.server.supervisor.getAllProcessInfo()
                if x['group'] == module and x['state'] == 20]
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
