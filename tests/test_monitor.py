import os
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)

import unittest
import mock
from core.parser import ConfParser


class TestMonitor(unittest.TestCase):

    @mock.patch.object(ConfParser, 'parse_rrcs')
    def setUp(self, mock_parse_rrcs):
        self.confParser = ConfParser()
        self.confParser.file = 'test_config'
        self.confParser.available_ris = set(['rrc15', 'rrc16', 'rrc17', 'rrc18', 'rrc19', 'rrc20', 'rrc21'])
        self.confParser.parse_file()

        mockSubprocess = mock.MagicMock()
        mockSubprocess.Popen.return_value = None

        sys.modules['subprocess'] = mockSubprocess
        from core.monitor import Monitor
        self.monitor = Monitor(self.confParser)

    def test_start(self):
        self.monitor.start()

        ripe, exa, live = [], [], []
        for proc in self.monitor.process_ids:
            _type, _info = proc[0].split()
            if _type == 'RIPEris':
                ripe.append(_info)
            elif _type == 'ExaBGP':
                exa.append(_info)
            elif _type == 'BGPStreamLive':
                live.append(_info)

# ['rrc16', 'rrc21', 'rrc17', 'rrc19', 'rrc20', 'rrc18', 'rrc15', 'rrc16', 'rrc21', 'rrc17', 'rrc19', 'rrc20', 'rrc18', 'rrc15'] ['192.168.1.1:5000', '192.168.5.1:5000'] ['routeviews,ris']
        self.assertEqual(ripe.sort(), ['rrc16', 'rrc21', 'rrc17', 'rrc19', 'rrc20', 'rrc18', 'rrc15', 'rrc16', 'rrc21', 'rrc17', 'rrc19', 'rrc20', 'rrc18', 'rrc15'].sort())
        self.assertEqual(exa.sort(), ['192.168.1.1:5000', '192.168.5.1:5000'].sort())
        self.assertEqual(live.sort(), ['routeviews,ris'].sort())

if __name__ == '__main__':
    unittest.main()
