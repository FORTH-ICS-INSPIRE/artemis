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
from core import ArtemisError


class TestConfParser(unittest.TestCase):

    @classmethod
    @mock.patch.object(ConfParser, 'parse_rrcs')
    def setUpClass(cls, mock_parse):
        cls.confParser = ConfParser()
        cls.confParser.file = 'tests/test_config'
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
        wrongParser = ConfParser()
        wrongParser.file = 'tests/test_wrong_config'

        with self.assertRaises(ArtemisError) as ex:
            wrongParser.parse_file()
        self.assertEqual(ex.exception.type, 'parsing-error')

    def test_valid_conf(self):
        obj = self.confParser.get_obj()
        group1 = obj['group1']
        group2 = obj['group2']

        self.assertEqual(group1['prefixes'], set([ipaddress.ip_network('10.0.0.0/24'), ipaddress.ip_network('20.0.0.0/24')]))
        self.assertEqual(group1['origin_asns'], set([1, 2]))
        self.assertEqual(group1['neighbors'], set([3, 4]))
        self.assertEqual(group1['mitigation'], 'manual')

        self.assertEqual(group2['prefixes'], set([ipaddress.ip_network('10.0.0.0/24'), ipaddress.ip_network('20.0.0.0/24'), ipaddress.ip_network('30.0.0.0/24')]))
        self.assertEqual(group2['origin_asns'], set([1, 2, 5]))
        self.assertEqual(group2['neighbors'], set([3]))
        self.assertEqual(group2['mitigation'], 'manual')

        defs = self.confParser.get_definitions()

        prefixes_group = defs['prefixes_group']
        asns_group = defs['asns_group']
        monitors_group = defs['monitors_group']

        self.assertEqual(monitors_group, self.confParser.get_monitors())
        self.assertEqual(prefixes_group['forth_prefixes'], set([ipaddress.ip_network('10.0.0.0/24'), ipaddress.ip_network('20.0.0.0/24')]))
        self.assertEqual(prefixes_group['sample_prefixes'], set([ipaddress.ip_network('30.0.0.0/24')]))
        self.assertEqual(asns_group['forth_asn'], set([1, 2]))
        self.assertEqual(asns_group['grnet_forth_upstream'], set([3]))
        self.assertEqual(asns_group['lamda_forth_upstream_back'], set([4]))
        self.assertEqual(asns_group['sample_asn'], set([5]))

        riperis = monitors_group['riperis']
        exabgp = monitors_group['exabgp']
        bgpstreamlive = monitors_group['bgpstreamlive']

        self.assertEqual(riperis, set(['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21']))
        self.assertEqual(exabgp, set([('192.168.1.1', 5000), ('192.168.5.1', 5000)]))
        self.assertEqual(bgpstreamlive, set(['routeviews', 'ris']))


    def test_process_field_prefixes(self):
        prefixes = self.confParser._process_field_prefixes(field='     1.0.0.0/24   ,2.0.0.0/24 ', where='', label='', definition=True)
        self.assertEqual(prefixes, set([ipaddress.ip_network('1.0.0.0/24'), ipaddress.ip_network('2.0.0.0/24')]))

        with self.assertRaises(ArtemisError) as ex:
            prefixes = self.confParser._process_field_prefixes(field='()1.0.0.024   ,2.0.0.0/24 ', where='', label='', definition=True)
        self.assertEqual(ex.exception.type, 'invalid-prefix')


        prefixes = self.confParser._process_field_prefixes(field='forth_prefixes   , sample_prefixes', where='', label='', definition=False)
        self.assertEqual(prefixes, set([ipaddress.ip_network('10.0.0.0/24'), ipaddress.ip_network('20.0.0.0/24'), ipaddress.ip_network('30.0.0.0/24')]))

        with self.assertRaises(ArtemisError) as ex:
            prefixes = self.confParser._process_field_prefixes(field='forth_kkk', where='', label='', definition=False)
        self.assertEqual(ex.exception.type, 'invalid-prefix')

    def test_process_field_asns(self):
        asns = self.confParser._process_field_asns(field='123, 321  ,    1 ', where='', definition=True)
        self.assertEqual(asns, set([123,321,1]))

        with self.assertRaises(ArtemisError) as ex:
            asns = self.confParser._process_field_asns(field='123, 321, -1', where='', definition=True)

        self.assertEqual(ex.exception.type, 'invalid-asn')
        with self.assertRaises(ArtemisError) as ex:
            asns = self.confParser._process_field_asns(field='123, 321, a', where='', definition=True)
        self.assertEqual(ex.exception.type, 'invalid-asn')

        asns = self.confParser._process_field_asns(field='forth_asn', where='', definition=False)
        self.assertEqual(asns, set([1,2])) 

        with self.assertRaises(ArtemisError) as ex:
            asns = self.confParser._process_field_asns(field='123, c, a', where='', definition=False)
        self.assertEqual(ex.exception.type, 'invalid-asn')


    def test_process_field_mitigation(self):
        pass


    def test_validate_options(self):
        pass


    def test_process_monitors(self):
        pass


if __name__ == '__main__':
    unittest.main()
