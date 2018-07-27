import os
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
os.environ['FLASK_CONFIGURATION'] = 'testing'

import unittest
import mock
from core.yamlparser import ConfigurationLoader
import logging


class TestMonitor(unittest.TestCase):

    @mock.patch('core.yamlparser.ConfigurationLoader')
    def setUp(self, mock_conf):
        logging.disable(logging.INFO)
        mockSubprocess = mock.MagicMock()
        mockSubprocess.Popen.return_value = None

        mock_conf.getRules.return_value = [
            {
                'prefixes': ['10.0.0.0/24', '10.0.0.0/25', '20.0.0.0/24'],
                'origin_asns': [1, 2],
                'neighbors': [3, 4, 5, 6],
                'mitigation': 'manual'
            }
        ]

        mock_conf.getMonitors.return_value = {
            'riperis': ['rrc01', 'rrc02', 'rrc03'],
            'bgpstreamlive': ['routeviews', 'ris'],
            'exabgp': [{'ip':'192.168.0.0', 'port':5000}],
            'bgpstreamhist': ['/tmp/test']
        }

        sys.modules['subprocess'] = mockSubprocess
        from core.monitor import Monitor
        self.monitor = Monitor(mock_conf)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_start(self):
        self.monitor.start()

        ripe, exa, live, hist = [], [], [], []
        for proc in self.monitor.process_ids:
            _info = proc[0].split()
            if _info[0] == 'RIPEris':
                ripe.append(_info)
            elif _info[0] == 'ExaBGP':
                exa.append(_info)
            elif _info[0] == 'BGPStreamLive':
                live.append(_info)
            elif _info[0] == 'BGPStreamHist':
                hist.append(_info)

        self.assertEqual(len(ripe), 6)
        self.assertEqual(len(exa), 1)
        self.assertEqual(len(live), 1)
        self.assertEqual(len(hist), 1)

        for r in ripe:
            self.assertFalse('10.0.0.0/25' in r[2])
        self.assertFalse('10.0.0.0/25' in ' '.join(exa[0]))
        self.assertFalse('10.0.0.0/25' in ' '.join(live[0]))
        self.assertFalse('10.0.0.0/25' in ' '.join(hist[0]))

if __name__ == '__main__':
    unittest.main()
