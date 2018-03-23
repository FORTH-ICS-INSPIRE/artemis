from configparser import ConfigParser
import os
import ipaddress

MAX_ASN_NUMBER = 397213


class ConfParser():

    def __init__(self):
        self.definitions_ = None
        self.obj_ = dict()
        self.file = 'configs/config'
        self.valid = True

        self.req_opt = ['prefixes', 'origin_asns']
        self.section_groups = ['prefixes_group', 'asns_group', 'monitors_group',
                               'local_mitigation_group', 'moas_mitigation_group']
        self.supported_fields = ['prefixes',
                                 'origin_asns', 'neighbors', 'mitigation']
        self.mitigation_types = ['deaggregate', 'outsource', 'manual']

        self.available_monitor_types = ['riperis', 'bgpmon', 'exabgp', 'bgpstreamhist', 'bgpstreamlive']
        self.available_ris = ['rrc18', 'rrc19', 'rrc20', 'rrc21']
        self.available_bgpstreamlive = ['routeviews', 'ris']
        self.valid_bgpmon = ['livebgp.netsec.colostate.edu', '5001']

        self.available_mitigation_fields = ['asn', 'ip', 'port']

        self.parser = ConfigParser()

        self.process_field = {
            'prefixes': self.process_field__prefixes,
            'origin_asns': self.process_field__asns,
            'neighbors': self.process_field__asns,
            'mitigation': self.proceess_field__mitigation
        }

        self.process_group = {
            'prefixes_group': self.process_field__prefixes,
            'asns_group': self.process_field__asns,
            'local_mitigation_group': self.process_local_and_moas_mitigation,
            'moas_mitigation_group': self.process_local_and_moas_mitigation,
            'monitors_group': self.process_monitors
        }

    def parse_file(self):
        print("Reading the config file..")
        self.parser.read(self.file)

        # Filtering sections blocks
        sections_list = self.parser.sections()
        sections_def_list = [
            section for section in sections_list if section in self.section_groups
        ]
        sections_other_list = [
            section for section in sections_list if section not in self.section_groups
        ]

        # Parse definition blocks
        self.definitions_ = self.parse_definition_blocks(sections_def_list)

        # Parse remaining blocks

        for section_name in sections_other_list:
            self.obj_[section_name] = dict()

            if(self.validate_options(section_name)):
                fields = self.parser.items(section_name)

                for field in fields:
                    type_of_field = field[0]

                    if(type_of_field not in self.supported_fields):
                        self.raise_error(
                            'field-wrong', section_name, type_of_field)

                    values_of_field = field[1]
                    self.obj_[section_name][type_of_field] = self.process_field[type_of_field](
                        values_of_field, section_name)

    def parse_definition_blocks(self, section_labels):

        ret_ = dict()

        for group in self.section_groups:
            ret_[group] = dict()

            if group in section_labels:
                fields = self.parser.items(group)

                for field in fields:
                    label = field[0]
                    values = field[1]
                    if(group == 'asns_group'):
                        ret_[group][label] = self.process_group[group](
                            values, group, definition=True)

                    else:
                        ret_[group][label] = self.process_group[group](
                            values, group, label=label, definition=True)

            else:
                pass

        return ret_

    def process_field__prefixes(
        self,
        field,
        where,
        label=None,
        definition=False
    ):

        prefixes = (''.join(field.split())).split(',')
        prefix_v = list()

        if(definition == True):
            for prefix in prefixes:
                try:
                    prefix_v.append(ipaddress.ip_network(prefix))
                except ValueError as e:
                    print("Error in config block: ", where, "-", str(label))
                    print(e)
                    self.valid = False

        else:
            for prefix in prefixes:
                try:
                    prefix_v.append(ipaddress.ip_network(prefix))
                except ValueError as e:
                    if(prefix in list(self.definitions_['prefixes_group'].keys())):
                        prefix_v += self.definitions_['prefixes_group'][prefix]
                    else:
                        # error
                        print("Not a valid group of prefixes")

        return prefix_v

    def process_field__asns(self, field, where, definition=False):
        try:
            if(definition == True):
                list_of_asns = list(
                    map(int, ''.join(field.split()).split(',')))
                if(all(self.valid_asn_number(item) for item in list_of_asns)):
                    return sorted(list(set(list_of_asns)))

            else:
                list_of_asns_ = ''.join(field.split()).split(',')
                list_of_asns = list()

                for asn in list_of_asns_:
                    if(asn in list(self.definitions_['asns_group'].keys())):
                        list_of_asns += self.definitions_['asns_group'][asn]
                    else:
                        if(self.valid_asn_number(int(asn))):
                            list_of_asns.append(int(asn))

                return sorted(list(set(list_of_asns)))

        except:
            self.raise_error('origin_asns-error', where)

    def proceess_field__mitigation(self, field, where):

        mitig_types = (''.join(field.split())).split(',')

        if(set(mitig_types).issubset(self.mitigation_types)):
            return mitig_types

        else:
            self.raise_error('mitigation-error-type', where)
            return False

    def validate_options(self, section_name):

        opt_list = self.parser.options(section_name)

        if(set(self.req_opt).issubset(opt_list)):
            return True

        else:
            self.raise_error('keyword-missing', section_name)
            return False

    def valid_asn_number(self, item):

        # https://www.iana.org/assignments/as-numbers/as-numbers.xhtml
        if(type(item) == int and item > 0 and item < MAX_ASN_NUMBER):
            return True
        return False

    def process_monitors(self, field, where, label, definition=None):

        try:
            if(label in self.available_monitor_types):

                if(label == 'riperis'):
                    riperis_ = (''.join(field.split())).split(',')

                    if(set(riperis_).issubset(self.available_ris)):
                        return riperis_
                    else:
                        list_ = list()
                        for ris_monitor in riperis_:
                            if(ris_monitor in self.available_ris):
                                list_.append(ris_monitor)
                            else:
                                print("Warning ", ris_monitor,
                                      " is not available.")

                        return list_

                elif(label == 'bgpmon'):
                    bgpmon_ = (''.join(field.split())).lstrip(
                        '(').rstrip(')').split(':')

                    if(len(bgpmon_) > 2):
                        print("Error only one value expected at ",
                              label, "in", where, ".")
                        self.valid = False

                    if(set(bgpmon_).issubset(self.valid_bgpmon)):
                        return [bgpmon_[0], int(bgpmon_[1])]

                elif(label == 'bgpstreamhist'):
                    bgpstreamhist_ = str(field)
                    if not os.path.isdir(bgpstreamhist_):
                        print("Error: bgpstreamhist csv dir is not valid!")
                        self.valid = False
                    else:
                        return bgpstreamhist_

                elif(label == 'bgpstreamlive'):
                    stream_projects_ = (''.join(field.split())).split(',')
                    if len(stream_projects_) == 0 or not set(stream_projects_).issubset(set(self.available_bgpstreamlive)):
                        print("Error: bgpstreamlive project(s) not supported!")
                        self.valid = False
                    else:
                        return stream_projects_

                elif(label == 'exabgp'):
                    exabgp_ = (''.join(field.split())).split(",")
                    list_ = list()
                    for entry in exabgp_:
                        ip = entry.split(':')[0].lstrip('(').rstrip(')')
                        port = int(entry.split(':')[1].lstrip('(').rstrip(')'))
                        list_.append([ip, port])

                    return list_
            else:
                # Error not a valid monitor
                pass
        except:
            print("ERROR!")

    def process_local_and_moas_mitigation(self, field, where, label, definition=None):

        # TODO: check with operators whether they need multiple local control endpoints,
        # multiple remote MOAS control endpoints, as well as selection per group
        # for now keep single dict for local, single dict for MOAS
        try:
            if(label in self.available_mitigation_fields):
                if(label == 'asn'):
                    if(self.valid_asn_number(int(field))):
                        return int(field)
                elif(label == 'port'):
                    return int(field)
                else:
                    return ipaddress.ip_address(field)
        except Exception as e:
            print("Error in config block: ", where, "-", str(label))
            print(e)
            self.valid = False

    def raise_error(self, type_of_error, where, field=None):

        if(type_of_error == "keyword-missing"):
            print(
                "Error -> Missing keyword 'prefixes' or 'origin_asns' on config block: ", where)
            self.valid = False

        elif(type_of_error == "field-wrong"):
            print("Error -> Found in '", where, "' the field -> '",
                  field,  " ' which is not supported.")
            print("List of supported fields: ", self.supported_fields)
            self.valid = False

        elif(type_of_error == "mitigation-error-type"):
            print("Error -> Found in '", where,
                  "' the mitigation field has an unsupported value.")
            print("List of supported fields: ", self.mitigation_types)
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

    def get_local_mitigation(self):
        return self.definitions_['local_mitigation_group']

    def get_moas_mitigation(self):
        return self.definitions_['moas_mitigation_group']
