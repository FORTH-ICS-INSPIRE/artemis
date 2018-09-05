#!/usr/bin/env python

import sys
import os
import argparse
import re


# TODO: implement better validity check
def is_valid_ipv4_prefix(pref_str):
    '''
    check the validity of a user-provided prefix
    :param pref_str:
    :return:
    '''
    if pref_str is not None:
        if re.match('^\d+\.\d+\.\d+\.\d+/\d+$', pref_str):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="send traffic destined to certain prefix towards GRE tunnel")
    parser.add_argument('-i', '--interface', dest='gre_interface',
                        type=str, help='local interface of GRE tunnel', default='gre1')
    parser.add_argument('-p', '--prefix', dest='prefix',
                        type=str, help='prefix to tunnel', required=True)
    parser.add_argument('-d', '--delete', dest='delete_route',
                        help='delete route', action='store_true')
    args = parser.parse_args()

    # http://ask.xmodulo.com/create-gre-tunnel-linux.html
    if not args.delete_route:
        os.system('/sbin/ip route add %s dev %s' %
                  (args.prefix, args.gre_interface))
    else:
        os.system('/sbin/ip route del %s dev %s' %
                  (args.prefix, args.gre_interface))


if __name__ == '__main__':
    main()
