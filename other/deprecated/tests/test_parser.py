import os
import unittest
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
os.environ['FLASK_CONFIGURATION'] = 'testing'

import mock
from core.yamlparser import ConfigurationLoader
import logging


class TestConfParser(unittest.TestCase):

    @classmethod
    @mock.patch.object(ConfigurationLoader, 'parse_rrcs')
    def setUpClass(cls, mock_parse):
        logging.disable(logging.INFO)
        cls.confParser = ConfigurationLoader()
        cls.confParser.file = 'tests/test_conf.yaml'
        cls.confParser.available_ris = {
            'rrc15',
            'rrc16',
            'rrc17',
            'rrc18',
            'rrc19',
            'rrc20',
            'rrc21'}
        cls.confParser.parse()

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    def setUp(self):
        pass

    def tearDown(self):
        pass

    @mock.patch.object(ConfigurationLoader, 'parse_rrcs')
    def test_isValid(self, mock_parse_rrcs):
        pass
        # wrongParser = ConfigurationLoader()
        # wrongParser.file = 'tests/test_wrong_config'
        #
        # with self.assertRaises(ArtemisError) as ex:
        #     wrongParser.parse_file()
        # self.assertEqual(ex.exception.type, 'parsing-error')

    def test_valid_conf(self):
        obj = self.confParser.getRules()
        group1 = obj[0]
        group2 = obj[1]

        self.assertEqual(group1['prefixes'], ['10.0.0.0/24', '20.0.0.0/24'])
        self.assertEqual(group1['origin_asns'], [1, 2])
        self.assertEqual(group1['neighbors'], [3, 4])
        self.assertEqual(group1['mitigation'], 'manual')

        self.assertEqual(
            group2['prefixes'], [
                '10.0.0.0/24', '20.0.0.0/24', '30.0.0.0/24'])
        self.assertEqual(group2['origin_asns'], [5, 1, 2])
        self.assertEqual(group2['neighbors'], [3])
        self.assertEqual(group2['mitigation'], 'manual')

        prefixes_group = self.confParser.getPrefixes()
        asns_group = self.confParser.getAsns()
        monitors_group = self.confParser.getMonitors()

        self.assertEqual(
            prefixes_group['forth_prefixes'], [
                '10.0.0.0/24', '20.0.0.0/24'])
        self.assertEqual(prefixes_group['sample_prefixes'], ['30.0.0.0/24'])
        self.assertEqual(asns_group['forth_asn'], [1, 2])
        self.assertEqual(asns_group['grnet_forth_upstream'], [3])
        self.assertEqual(asns_group['lamda_forth_upstream_back'], [4])
        self.assertEqual(asns_group['sample_asn'], [5])

        riperis = monitors_group['riperis']
        exabgp = monitors_group['exabgp']
        bgpstreamlive = monitors_group['bgpstreamlive']

        self.assertEqual(
            riperis, [
                'rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21'])
        self.assertEqual(exabgp, [{'ip': '192.168.1.1', 'port': 5000}, {
                         'ip': '192.168.5.1', 'port': 5000}])
        self.assertEqual(bgpstreamlive, ['routeviews', 'ris'])


if __name__ == '__main__':
    unittest.main()
