from configparser import ConfigParser, ParsingError, MissingSectionHeaderError
import os
import sys
import ipaddress
import traceback
from socketIO_client_nexus import SocketIO
import re
from core import ArtemisError

check_asn = lambda asn : asn > 0 and asn < 4294967295

class ConfParser():

    def __init__(self):
        self.definitions_ = None
        self.obj_ = dict()
        self.file = 'configs/config'

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
            'prefixes': self._process_field_prefixes,
            'origin_asns': self._process_field_asns,
            'neighbors': self._process_field_asns,
            'mitigation': self._process_field_mitigation
        }

        self.process_group = {
            'prefixes_group': self._process_field_prefixes,
            'asns_group': self._process_field_asns,
            'monitors_group': self._process_monitors
        }

    def parse_rrcs(self):
        try:
            socket_io = SocketIO('http://stream-dev.ris.ripe.net/stream', wait_for_connection=False)
            def on_msg(msg):
                self.available_ris = set(msg)
                socket_io.disconnect()
            socket_io.on('ris_rrc_list', on_msg)
            socket_io.wait(seconds=3)
        except Exception:
            print('[!] RIPE RIS server is down. Try again later..')

    def parse_file(self):
        try:
            self.parser.read(self.file)
        except ParsingError as e:
            raise ArtemisError('parsing-error', e)
        except MissingSectionHeaderError as e:
            raise ArtemisError('missing-section-header-error', e)

        # Filtering sections blocks
        sections_list = self.parser.sections()
        sections_def_list = [
            section for section in sections_list if section in self.section_groups
        ]
        sections_other_list = [
            section for section in sections_list if section not in self.section_groups
        ]

        # Parse definition blocks
        self.definitions_ = self._parse_definition_blocks(sections_def_list)

        # Parse remaining blocks
        for section_name in sections_other_list:
            self.obj_[section_name] = dict()

            if self._validate_options(section_name):
                fields = self.parser.items(section_name)

                for field in fields:
                    type_of_field = field[0]

                    if type_of_field not in self.supported_fields:
                        raise ArtemisError('wrong-field', '[{}][{}] for {}'.format(section_name, field, type_of_field))
                    values_of_field = field[1]
                    self.obj_[section_name][type_of_field] = self.process_field[type_of_field](
                        values_of_field, section_name)

    def _parse_definition_blocks(self, section_labels):
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

        return ret_

    def _process_field_prefixes(
        self,
        field,
        where,
        label=None,
        definition=False
    ):
        if definition:
            prefixes = [x.strip() for x in field.split(',')]
        else:
            tmp_prefixes = [x.strip() for x in field.split(',')]
            prefixes = [x for prefix in tmp_prefixes for x in self.definitions_['prefixes_group'].get(prefix, [prefix])]

        try:
            prefixes = set(map(ipaddress.ip_network, prefixes))
        except ValueError as e:
            raise ArtemisError('invalid-prefix', '[{}][{}][{}] with {}'.format(field, where, label, e))
        return prefixes

    def _process_field_asns(self, field, where, definition=False):
        list_of_asns = [x.strip() for x in field.split(',')]
        if definition:
            asn_list = [asn for asn in list_of_asns]
        else:
            asn_list = [x for asn in list_of_asns for x in self.definitions_['asns_group'].get(asn, [asn])]

        try:
            asn_list = [int(asn) for asn in asn_list]
        except ValueError as e:
            raise ArtemisError('invalid-asn', '[{}][{}]'.format(field, where))
        if not all(map(check_asn, asn_list)):
            raise ArtemisError('invalid-asn', '[{}][{}]'.format(field, where))
        return set(asn_list)

        # raise ArtemisError('origin_asns-error', '{}'.format(where))

    def _process_field_mitigation(self, field, where):
        mitigation_action = str(field)
        if mitigation_action == 'manual' or os.path.isfile(mitigation_action):
            return mitigation_action

        else:
            raise ArtemisError('mitigation-error', '{}'.format(where))

    def _validate_options(self, section_name):
        opt_list = self.parser.options(section_name)

        if set(self.req_opt).issubset(opt_list):
            return True
        else:
            raise ArtemisError('keyword-missing', '{}'.format(section_name))

    def _process_monitors(self, field, where, label, definition=None):
        try:
            if label in self.available_monitor_types:

                if label == 'riperis':
                    riperis_ = set([x.strip() for x in field.split(',')])

                    for unavailable in riperis_.difference(self.available_ris):
                        print('[!] Warning: unavailable monitor {}'.format(unavailable),
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
                        raise ArtemisError('bgpstreamhist', 'csv dir is not valid')
                    else:
                        return bgpstreamhist_

                elif label == 'bgpstreamlive':
                    stream_projects_ = set([x.strip() for x in field.split(',')])
                    if len(stream_projects_) == 0 or not stream_projects_.issubset(self.available_bgpstreamlive):
                        raise ArtemisError('bgpstreamlive','project(s) not supported')
                    else:
                        return stream_projects_

                elif label == 'exabgp':
                    exa_pattern = re.compile('(?:([0-9.]+) ?: ?([0-9]+))')
                    entries = re.findall(exa_pattern, field)
                    entries = set(map(lambda a: (a[0], int(a[1])), entries))
                    return entries
            else:
                # Error not a valid monitor
                raise ArtemisError('Invalid monitor', '')
        except ParsingError as e:
            raise ArtemisError('Parsing Error', e)

    def get_obj(self):
        return self.obj_

    def get_definitions(self):
        return self.definitions_

    def get_monitors(self):
        return self.definitions_['monitors_group']
