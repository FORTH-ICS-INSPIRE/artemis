#!/usr/bin/python

import sys, os
import argparse
import re
import telnetlib
import getpass


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


def announce_prefix(telnet_con, prefix, local_as, withdraw=False):
    '''
    announce (or remove) a prefix to the localAS BGP speaker
    :param telnet_con: telnet connection to BGP speaker
    :param prefix: prefix to announce
    :param local_as: ASN of BGP speaker (which we configure)
    '''
    telnet_con.write("en\n")
    telnet_con.read_until("# ")
    telnet_con.write("configure terminal\n")
    telnet_con.read_until("(config)# ")
    telnet_con.write("router bgp {}\n".format(local_as))
    telnet_con.read_until("(config-router)# ")
    wp = ""
    if withdraw:
        wp = "no "
    telnet_con.write("{}network {}\n".format(wp, prefix))
    telnet_con.read_until("(config-router)# ")
    telnet_con.write("end\n")
    telnet_con.read_until("# ")
    telnet_con.write("exit\n")


def main():
    parser = argparse.ArgumentParser(description="send a prefix announce(/removal) command via telnet to BGP router (quagga)")
    parser.add_argument('-th', '--thost', dest='telnet_host', type=str, help='host to telnet', default='localhost')
    # https://www.systutorials.com/docs/linux/man/8-bgpd/
    parser.add_argument('-tp', '--tport', dest='telnet_port', type=int, help='port to telnet', default=2605)
    parser.add_argument('-la', '--lasn', dest='local_asn', type=int, help='local AS of BGP speaker', required=True)
    parser.add_argument('-ap', '--aprefix', dest='announce_prefix', type=str, help='prefix to announce', required=True)
    parser.add_argument('-w', '--withdraw', dest='withdraw_prefix', help='withdraw prefix', action='store_true')
    args = parser.parse_args()

    print('Connecting to {} {}'.format(args.telnet_host, args.telnet_port))
    #print("Enter your telnet password")
    #telnet_pw = getpass.getpass()
    telnet_pw = 'sdnip' # hardcode for now
    tn = telnetlib.Telnet(args.telnet_host, args.telnet_port)
    tn.read_until("Password: ")
    tn.write("%s\n" % telnet_pw)
    tn.read_until("bgp> ")

    if is_valid_ipv4_prefix(args.announce_prefix):
        announce_prefix(telnet_con=tn,
                        prefix=args.announce_prefix,
                        local_as=args.local_asn,
                        withdraw=args.withdraw_prefix)
        info_str = ""
        if not args.withdraw_prefix:
            info_str += "Announced"
        else:
            info_str += "Withdrew"
        print("{} prefix '{}' from AS {}".format(info_str, args.announce_prefix, args.local_asn))
    else:
        print("Invalid prefix '{}'".format(args.announce_prefix))


if __name__ == '__main__':
    main()

