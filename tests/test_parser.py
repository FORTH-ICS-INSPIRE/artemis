import os
import unittest
import sys
import ipaddress

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)

import mock
from core.parser import ConfParser

class TestConfParser(unittest.TestCase):
    def setUp(self):
        self.confParser = ConfParser()
        self.confParser.file = 'test_config'
        self.confParser.available_ris = ['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21']
        self.confParser.parse_file()

    def test_isValid(self):
        assert self.confParser.isValid()

    @mock.patch('core.parser.ConfParser.__parse_rrcs')
    def test_get_obj(self):
        obj = self.confParser.get_obj()
        group1 = obj['group1']
        group2 = obj['group2']
        # {'prefixes': [IPv4Network('139.91.0.0/16')], 'origin_asns': [8522], 'neighbors': [5408, 56910], 'mitigation': 'manual'}
        assert group1['prefixes'] == [ipaddress.ip_network('139.91.0.0/16')]
        assert group1['origin_asns'] == [8522]
        assert group1['neighbors'] == [5408, 56910]
        assert group1['mitigation'] == 'manual'

        # {'prefixes': [IPv4Network('139.91.0.0/16'), IPv4Network('139.91.0.0/17')], 'origin_asns': [8522, 12345], 'neighbors': [5408], 'mitigation': 'manual'}
        assert group2['prefixes'] == [ipaddress.ip_network('139.91.0.0/16'), ipaddress.ip_network('139.91.0.0/17')]
        assert group2['origin_asns'] == [8522, 12345]
        assert group2['neighbors'] == [5408]
        assert group2['mitigation'] == 'manual'

    def test_get_definitions(self):
        defs = self.confParser.get_definitions()
        # {'prefixes_group': {'forth_prefixes': [IPv4Network('139.91.0.0/16')], 'sample_prefixes': [IPv4Network('139.91.0.0/17')]}, 'asns_group': {'forth_asn': [8522], 'grnet_forth_upstream': [5408], 'lamda_forth_upstream_back': [56910], 'sample_asn': [12345]}, 'monitors_group': {'riperis': ['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21'], 'exabgp': [['192.168.1.1', 5000], ['192.168.5.1', 5000]], 'bgpstreamlive': ['routeviews', 'ris']}}

        prefixes_group = defs['prefixes_group']
        asns_group = defs['asns_group']
        monitors_group = defs['monitors_group']

        assert monitors_group == self.confParser.get_monitors()
        assert prefixes_group['forth_prefixes'] == [ipaddress.ip_network('139.91.0.0/16')] and prefixes_group['sample_prefixes'] == [ipaddress.ip_network('139.91.0.0/17')]

        assert asns_group['forth_asn'] == [8522] and asns_group['grnet_forth_upstream'] == [5408] and asns_group['lamda_forth_upstream_back'] == [56910] and asns_group['sample_asn'] == [12345]

        riperis = monitors_group['riperis']
        exabgp = monitors_group['exabgp']
        bgpstreamlive = monitors_group['bgpstreamlive']

        assert riperis == ['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21']
        assert exabgp == [['192.168.1.1', 5000], ['192.168.5.1', 5000]]
        assert bgpstreamlive == ['routeviews', 'ris']

if __name__ == '__main__':
    unittest.main()
