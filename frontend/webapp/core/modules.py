from webapp.utils import SUPERVISOR_HOST, SUPERVISOR_PORT
import logging
from xmlrpc.client import ServerProxy

log = logging.getLogger('webapp_logger')

intervals = (
    ('W', 604800),  # 60 * 60 * 24 * 7
    ('D', 86400),    # 60 * 60 * 24
    ('H', 3600),    # 60 * 60
    ('M', 60),
    ('S', 1),
)


def display_time(seconds, granularity=2):
    if seconds is None:
        return 'N/A'
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

    def __call__(self, module, action):
        try:
            if module == 'all':
                if action == 'start':
                    res = self.server.supervisor.startAllProcesses
                elif action == 'stop':
                    res = self.server.supervisor.stopAllProcesses
            else:
                if action == 'start':
                    res = self.server.supervisor.startProcess[module]
                elif action == 'stop':
                    res = self.server.supervisor.stopProcess[module]
        except Exception as e:
            res = str(e)
        return res

    def is_up_or_running(self, module):
        try:
            response = self.server.supervisor.getProcessInfo(module)
            return response['state'] == 20
        except Exception:
            log.exception('exception')
            return False

    def get_response_all(self):
        ret_response = {}
        response = self.server.supervisor.getAllProcessInfo()
        for module in response:
            ret_response[module['name']] = {
                'status': module['state'] == 20,
                'uptime': display_time(module['now'] - module['start'])
            }
        return ret_response

    def get_response_formatted_all(self):
        return self.get_response_all()
