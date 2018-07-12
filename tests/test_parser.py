import os
import unittest
import sys
import ipaddress

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)

import mock
from core.parser import ConfParser
import configparser


class TestConfParser(unittest.TestCase):

    @classmethod
    @mock.patch.object(ConfParser, 'parse_rrcs')
    def setUpClass(cls, mock_parse):
        cls.confParser = ConfParser()
        cls.confParser.file = 'test_config'
        cls.confParser.available_ris = set(['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21'])
        cls.confParser.parse_file()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        pass

    def tearDown(self):
        pass

    @mock.patch.object(ConfParser, 'parse_rrcs')
    def test_isValid(self, mock_parse_rrcs):
        print('[!] Testing a valid configuration file')
        self.assertTrue(self.confParser.isValid())

        print('[!] Testing an invalid configuration file')
        wrongParser = ConfParser()
        wrongParser.file = 'test_wrong_config'
        self.assertRaises(configparser.ParsingError, wrongParser.parse_file)

    def test_get_obj(self):
        print('[!] Testing object fields of the configuration')
        obj = self.confParser.get_obj()
        group1 = obj['group1']
        group2 = obj['group2']
        # {'prefixes': [IPv4Network('139.91.0.0/16')], 'origin_asns': [8522], 'neighbors': [5408, 56910], 'mitigation': 'manual'}
        self.assertEqual(group1['prefixes'], [ipaddress.ip_network('139.91.0.0/16')])
        self.assertEqual(group1['origin_asns'], [8522])
        self.assertEqual(group1['neighbors'], [5408, 56910])
        self.assertEqual(group1['mitigation'], 'manual')

        # {'prefixes': [IPv4Network('139.91.0.0/16'), IPv4Network('139.91.0.0/17')], 'origin_asns': [8522, 12345], 'neighbors': [5408], 'mitigation': 'manual'}
        self.assertEqual(group2['prefixes'], [ipaddress.ip_network('139.91.0.0/16'), ipaddress.ip_network('139.91.0.0/17')])
        self.assertEqual(group2['origin_asns'], [8522, 12345])
        self.assertEqual(group2['neighbors'], [5408])
        self.assertEqual(group2['mitigation'], 'manual')

    def test_get_definitions(self):
        print('[!] Testing definitions of the configuration')
        defs = self.confParser.get_definitions()
        # {'prefixes_group': {'forth_prefixes': [IPv4Network('139.91.0.0/16')], 'sample_prefixes': [IPv4Network('139.91.0.0/17')]}, 'asns_group': {'forth_asn': [8522], 'grnet_forth_upstream': [5408], 'lamda_forth_upstream_back': [56910], 'sample_asn': [12345]}, 'monitors_group': {'riperis': ['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21'], 'exabgp': [['192.168.1.1', 5000], ['192.168.5.1', 5000]], 'bgpstreamlive': ['routeviews', 'ris']}}

        prefixes_group = defs['prefixes_group']
        asns_group = defs['asns_group']
        monitors_group = defs['monitors_group']

        self.assertEqual(monitors_group, self.confParser.get_monitors())
        self.assertEqual(prefixes_group['forth_prefixes'], [ipaddress.ip_network('139.91.0.0/16')])
        self.assertEqual(prefixes_group['sample_prefixes'], [ipaddress.ip_network('139.91.0.0/17')])
        self.assertEqual(asns_group['forth_asn'], [8522])
        self.assertEqual(asns_group['grnet_forth_upstream'], [5408])
        self.assertEqual(asns_group['lamda_forth_upstream_back'], [56910])
        self.assertEqual(asns_group['sample_asn'], [12345])

        riperis = monitors_group['riperis']
        exabgp = monitors_group['exabgp']
        bgpstreamlive = monitors_group['bgpstreamlive']

        self.assertEqual(riperis, set(['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21']))
        self.assertEqual(exabgp, set([('192.168.1.1', 5000), ('192.168.5.1', 5000)]))
        self.assertEqual(bgpstreamlive, set(['routeviews', 'ris']))

if __name__ == '__main__':
    unittest.main()
