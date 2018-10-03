#!/usr/bin/env python

import socket
import sys
import re
import time
import argparse
import os


PY_BIN = '/usr/bin/python'
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
QC_PY = '%s/quagga_command.py' % (str(CURRENT_DIR))
GR_PY = '%s/send_to_gre_tun.py' % (str(CURRENT_DIR))


# TODO: implement better validity check
def is_valid_ipv4_address(ip_str=None):
    if ip_str is not None:
        if re.match('^\d+\.\d+\.\d+\.\d+$', ip_str):
            return True
    return False


# TODO: implement better validity check
def is_valid_ipv4_prefix(pref_str):
    if pref_str is not None:
        if re.match('^\d+\.\d+\.\d+\.\d+/\d+$', pref_str):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="receive a MOAS command from MOAS sender")
    parser.add_argument('-li', '--lip', dest='listen_ip',
                        type=str, help='listen ip', required=True)
    parser.add_argument('-lp', '--lport', dest='listen_port',
                        type=int, help='listen port', required=True)
    parser.add_argument('-la', '--lasn', dest='local_asn',
                        type=int, help='local asn', required=True)
    parser.add_argument('-b', '--buffer', dest='buffer_size',
                        type=int, help='buffer size', default=1024)
    args = parser.parse_args()

    if not is_valid_ipv4_address(args.listen_ip):
        print("Invalid listen ip address '%s'" % args.listen_ip)
        sys.exit(1)

    print("MOAS agent TCP listen IP: %s" % args.listen_ip)
    print("MOAS agent TCP listen port: %d" % args.listen_port)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((args.listen_ip, args.listen_port))
        sock.listen(1)

        while True:
            conn, addr = sock.accept()
            print('Connection established with %s' % str(addr[0]))

            data = conn.recv(args.buffer_size)
            if data:
                print("Received '%s' from host %s from port %s over TCP." %
                      (data, addr[0], addr[1]))
                command = str(data).split('-')
                if len(command) != 2 or command[1] not in ['yes', 'no']:
                    print('Unexpected/invalid message received!')
                    print('Expected: IPv4 prefix-[yes/no]')
                    continue

                if is_valid_ipv4_prefix(command[0]):
                    prefix = str(command[0])
                    print("Valid prefix to moas: '%s'" % prefix)
                else:
                    print('Unexpected/invalid prefix received!')
                    continue

                if command[1] == 'yes':
                    print("Anouncing prefix '%s' locally from ASN %d" %
                          (prefix, args.local_asn))
                    os.system('%s %s -la %d -ap %s ' %
                              (PY_BIN, QC_PY, args.local_asn, prefix))
                    time.sleep(1)
                    os.system('%s %s -p %s' % (PY_BIN, GR_PY, prefix))
                    print(
                        'Activated GRE tunnel from MOAS helper for prefix %s' % prefix)
                else:
                    print("Unanouncing prefix '%s' locally from ASN %d" %
                          (prefix, args.local_asn))
                    os.system('%s %s -la %d -ap %s -w' %
                              (PY_BIN, QC_PY, args.local_asn, prefix))
                    time.sleep(1)
                    os.system('%s %s -p %s -d' % (PY_BIN, GR_PY, prefix))
                    print(
                        'Deactivated GRE tunnel from MOAS helper for prefix %s' % prefix)
            conn.close()
    except BaseException:
        print("Error with connection!")


if __name__ == '__main__':
    main()
