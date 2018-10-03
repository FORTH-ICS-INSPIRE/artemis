#!/usr/bin/env python

import socket
import sys
import re
import time
import argparse


# TODO: implement better validity check
def is_valid_ipv4_address(ip_str=None):
    if ip_str is not None:
        if re.match('^\d+\.\d+\.\d+\.\d+$', ip_str):
            return True
    return False


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
        description="send a MOAS command to MOAS receiver")
    parser.add_argument('-r', '--receiver', dest='moas_receiver',
                        type=str, help='receiver ip', required=True)
    parser.add_argument('-p', '--port', dest='moas_port',
                        type=int, help='receiver port', required=True)
    parser.add_argument('-m', '--moas_prefix', dest='moas_prefix',
                        type=str, help='moas prefix', required=True)
    parser.add_argument('-w', '--withdraw', dest='moas_withdraw',
                        help='withdraw moas prefix', action='store_true')
    args = parser.parse_args()

    if not is_valid_ipv4_address(args.moas_receiver):
        print("Invalid receiver ip address '%s'" % args.moas_receiver)
        sys.exit(1)

    if not is_valid_ipv4_prefix(args.moas_prefix):
        print("Invalid moas prefix '%s'" % args.moas_prefix)
        sys.exit(1)

    print("MOAS TCP target IP: %s" % args.moas_receiver)
    print("MOAS TCP target port: %d" % args.moas_port)
    print("MOAS prefix: '%s'" % args.moas_prefix)
    print("MOAS withdraw: %s" % args.moas_withdraw)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.moas_receiver, args.moas_port))
        if not args.moas_withdraw:
            sock.send(args.moas_prefix + "-yes")
        else:
            sock.send(args.moas_prefix + "-no")
        sock.close()
        print("Message sent!")
    except BaseException:
        print("Could not connect!")


if __name__ == '__main__':
    main()
