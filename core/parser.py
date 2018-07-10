from configparser import ConfigParser, ParsingError
import os
import sys
import ipaddress
import traceback
from socketIO_client_nexus import SocketIO
import re

MAX_ASN_NUMBER = 397213

class ConfParser():

    def __init__(self):
        self.definitions_ = None
        self.obj_ = dict()
        self.file = 'configs/config'
        self.valid = True

        self.req_opt = set(['prefixes', 'origin_asns'])
        self.section_groups = set(['prefixes_group', 'asns_group', 'monitors_group'])
        self.supported_fields = set(['prefixes',
                                 'origin_asns', 'neighbors', 'mitigation'])
        self.available_monitor_types = set(
            ['riperis', 'bgpmon', 'exabgp', 'bgpstreamhist', 'bgpstreamlive'])
        self.available_ris = set()

        self.parse_rrcs()

        self.available_bgpstreamlive = set(['routeviews', 'ris'])
        self.valid_bgpmon = set([('livebgp.netsec.colostate.edu','5001')])

        self.parser = ConfigParser()

        self.process_field = {
            'prefixes': self.__process_field_prefixes,
            'origin_asns': self.__process_field_asns,
            'neighbors': self.__process_field_asns,
            'mitigation': self.__process_field_mitigation
        }

        self.process_group = {
            'prefixes_group': self.__process_field_prefixes,
            'asns_group': self.__process_field_asns,
            'monitors_group': self.__process_monitors
        }

    def parse_rrcs(self):
        with SocketIO('http://stream-dev.ris.ripe.net/stream') as socket_io:
            def on_msg(msg):
                self.available_ris = set(msg)
                socket_io.disconnect()

            socket_io.on('ris_rrc_list', on_msg)
            socket_io.wait()

    def parse_file(self):
        try:
            self.parser.read(self.file)
        except ParsingError as e:
            print('[!] Configuration file could not be parsed.\nException: {}'.format(e),
                    file=sys.stderr)
            raise e

        # Filtering sections blocks
        sections_list = self.parser.sections()
        sections_def_list = [
            section for section in sections_list if section in self.section_groups
        ]
        sections_other_list = [
            section for section in sections_list if section not in self.section_groups
        ]

        # Parse definition blocks
        self.definitions_ = self.__parse_definition_blocks(sections_def_list)

        # Parse remaining blocks

        for section_name in sections_other_list:
            self.obj_[section_name] = dict()

            if self.__validate_options(section_name):
                fields = self.parser.items(section_name)

                for field in fields:
                    type_of_field = field[0]

                    if type_of_field not in self.supported_fields:
                        self.__raise_error(
                            'field-wrong', section_name, type_of_field)

                    values_of_field = field[1]
                    self.obj_[section_name][type_of_field] = self.process_field[type_of_field](
                        values_of_field, section_name)

    def __parse_definition_blocks(self, section_labels):
        ret_ = dict()

        for group in self.section_groups:
            ret_[group] = dict()

            if group in section_labels:
                fields = self.parser.items(group)

                for field in fields:
                    label = field[0]
                    values = field[1]
                    if group == 'asns_group':
                        ret_[group][label] = self.process_group[group](
                            values, group, definition=True)

                    else:
                        ret_[group][label] = self.process_group[group](
                            values, group, label=label, definition=True)

            else:
                pass

        return ret_

    def __process_field_prefixes(
        self,
        field,
        where,
        label=None,
        definition=False
    ):
        prefixes = field.split(', ')
        prefix_v = list()

        if definition == True:
            for prefix in prefixes:
                try:
                    prefix_v.append(ipaddress.ip_network(prefix))
                except ValueError as e:
                    print('[!] Error in config block: {} - {}.\nException: {}'.format(where, label, e),
                            file=sys.stderr)
                    self.valid = False

        else:
            for prefix in prefixes:
                try:
                    prefix_v.append(ipaddress.ip_network(prefix))
                except ValueError as e:
                    if prefix in self.definitions_['prefixes_group']:
                        prefix_v += self.definitions_['prefixes_group'][prefix]
                    else:
                        # error
                        print('[!] Not a valid group of prefixes', file=sys.stderr)

        return prefix_v

    def __process_field_asns(self, field, where, definition=False):
        try:
            if definition:
                list_of_asns = list(map(int, field.split(', ')))
                if all(map(self.__valid_asn_number, list_of_asns)):
                    return sorted(list(set(list_of_asns)))

            else:
                list_of_asns_ = field.split(', ')
                list_of_asns = []
                for asn in list_of_asns_:
                    if asn in self.definitions_['asns_group']:
                        list_of_asns += self.definitions_['asns_group'][asn]
                    else:
                        if self.__valid_asn_number(int(asn)):
                            list_of_asns.append(int(asn))

                return sorted(list(set(list_of_asns)))

        except Exception as e:
            print(e)
            self.__raise_error('origin_asns-error', where)

    def __process_field_mitigation(self, field, where):
        mitigation_action = str(field)
        if mitigation_action == 'manual' or os.path.isfile(mitigation_action):
            return mitigation_action

        else:
            self.__raise_error('mitigation-error', where)
            return False

    def __validate_options(self, section_name):
        opt_list = self.parser.options(section_name)

        if set(self.req_opt).issubset(opt_list):
            return True

        else:
            self.__raise_error('keyword-missing', section_name)
            return False

    def __valid_asn_number(self, item):
        # https://www.iana.org/assignments/as-numbers/as-numbers.xhtml
        if type(item) == int and item > 0 and item < MAX_ASN_NUMBER:
            return True
        return False

    def __process_monitors(self, field, where, label, definition=None):
        try:
            if label in self.available_monitor_types:

                if label == 'riperis':
                    riperis_ = set(field.split(', '))

                    for unavailable in riperis_.difference(self.available_ris):
                        print('[!] Warning unavailable monitor: {}'.format(unavailable),
                                file=sys.stderr)

                    return riperis_.intersection(self.available_ris)
                elif label == 'bgpmon':
                    bgpmon_pattern = re.compile('(?:([a-zA-Z0-9.]+) ?: ?([0-9]+))')

                    entries = re.findall(bgpmon_pattern, field)

                    if set(entries).issubset(self.valid_bgpmon):
                        return (entries[0][0], int(entries[0][1]))

                elif label == 'bgpstreamhist':
                    bgpstreamhist_ = str(field)
                    if not os.path.isdir(bgpstreamhist_):
                        print("Error: bgpstreamhist csv dir is not valid!")
                        self.valid = False
                    else:
                        return bgpstreamhist_

                elif label == 'bgpstreamlive':
                    stream_projects_ = field.split(', ')
                    if len(stream_projects_) == 0 or not set(stream_projects_).issubset(set(self.available_bgpstreamlive)):
                        print("Error: bgpstreamlive project(s) not supported!")
                        self.valid = False
                    else:
                        return set(stream_projects_)

                elif label == 'exabgp':
                    exa_pattern = re.compile('(?:([0-9.]+) ?: ?([0-9]+))')
                    entries = re.findall(exa_pattern, field)
                    entries = set(map(lambda a: (a[0], int(a[1])), entries))
                    return entries
            else:
                # Error not a valid monitor
                pass
        except ParsingError as e:
            print('[!] Parsing Error {}'.format(e))
            raise e

    def __raise_error(self, type_of_error, where, field=None):

        if(type_of_error == "keyword-missing"):
            print(
                "Error -> Missing keyword 'prefixes' or 'origin_asns' on config block: ", where)
            self.valid = False

        elif(type_of_error == "field-wrong"):
            print("Error -> Found in '", where, "' the field -> '",
                  field,  " ' which is not supported.")
            print("List of supported fields: ", self.supported_fields)
            self.valid = False

        elif(type_of_error == "mitigation-error"):
            print("Error -> Found in '", where,
                  "' the mitigation field points to a non-existent script.")
            self.valid = False

        elif(type_of_error == 'origin_asns-error'):
            print("Error in origin_asns config block: ", where)
            print("Found a wrong ASN number.")
            self.valid = False

        elif(type_of_error == 'neighbors-error'):
            print("Error in neighbors config block: ", where)
            print("Found a wrong ASN number.")
            self.valid = False

        elif(type_of_error == 'asns_group-error'):
            print("Error in asns_group config block: ", where)
            print("Found a wrong ASN number.")
            self.valid = False

    def isValid(self):
        return self.valid

    def get_obj(self):
        return self.obj_

    def get_definitions(self):
        return self.definitions_

    def get_monitors(self):
        return self.definitions_['monitors_group']
