import os
import unittest
import sys

this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)

import mock
from core.parser import ConfParser
from core.monitor import Monitor

class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.confParser = ConfParser()
        self.confParser.file = 'test_config'
        self.confParser.parse_file()
        self.monitor = Monitor(self.confParser)

    @mock.patch('core.monitor.Monitor.init_ris_instances')
    @mock.patch('core.monitor.Monitor.init_exabgp_instance')
    @mock.patch('core.monitor.Monitor.init_bgpstreamhist_instance')
    @mock.patch('core.monitor.Monitor.init_bgpstreamlive_instance')
    def test_start(self, a, b, c, d):
        self.monitor.start()

    # @mock.patch('core.monitor.Monitor.init_ris_instances')
    # @mock.patch('core.monitor.Monitor.init_exabgp_instance')
    # @mock.patch('core.monitor.Monitor.init_bgpstreamhist_instance')
    # @mock.patch('core.monitor.Monitor.init_bgpstreamlive_instance')
    def test_stop(self):
        self.monitor.stop()

if __name__ == '__main__':
    unittest.main()
