#!/usr/bin/env python
import traceback
import argparse
from xmlrpc.client import ServerProxy


class ControllerCLI(object):

    def call(self, module, action):
        try:
            server = ServerProxy('http://localhost:9001/RPC2')
            if action == 'start':
                res = server.supervisor.startProcess[module]
            elif action == 'stop':
                res = server.supervisor.stopProcess[module]
        except Exception as e:
            res = str(e)
        return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Module Controller Script')
    parser.add_argument('-m', '--module', type=str, dest='module', required=True,
                        help='Module name for the desired action')
    parser.add_argument('-a', '--action', type=str, dest='action', required=True,
                        help='Action to be sent (start, stop, status)')

    args = parser.parse_args()
    try:
        cli = ControllerCLI()
        print(' [x] Requesting')
        response = cli.call(args.module, args.action)
        print(' [.] Got {}'.format(response))
    except BaseException:
        traceback.print_exc()
