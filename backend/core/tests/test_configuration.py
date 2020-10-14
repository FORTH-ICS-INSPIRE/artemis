import unittest
from unittest.mock import MagicMock
from unittest.mock import mock_open
from unittest.mock import patch

import configuration

TEST_CONF_DATA = """
prefixes:
    prefix_1: &prefix_1
    - 10.0.0.0/8
    - 10.1.0.0/16
asns:
    origins: &origins
    - 1
    neighbors: &neighbors
    - 2
    - 3
rules:
    - prefixes:
      - *prefix_1
      origin_asns:
      - *origins
      neighbors:
      - *neighbors
      mitigation: manual
    - prefixes:
      - *prefix_1
      origin_asns:
      - *origins
      prepend_seq:
      - [4, 3, 2]
      - [8, 7, 6, 5]
      mitigation: manual
"""


class ConfigurationTester(unittest.TestCase):
    @patch("builtins.open", mock_open(read_data=TEST_CONF_DATA))
    @patch("redis.Redis", MagicMock())
    @patch("configuration.ping_redis", MagicMock())
    def setUp(self) -> None:
        self.worker = configuration.Configuration.Worker(MagicMock())

    def test_prefixes(self):
        self.assertEqual(
            set(self.worker.data["prefixes"]["prefix_1"]),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )

    def test_asns(self):
        self.assertEqual(set(self.worker.data["asns"]["origins"]), set([1]))
        self.assertEqual(set(self.worker.data["asns"]["neighbors"]), set([2, 3]))

    def test_simple_rule_neighbors(self):
        self.assertEqual(
            set(self.worker.data["rules"][0]["prefixes"]),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )
        self.assertEqual(set(self.worker.data["rules"][0]["origin_asns"]), set([1]))
        self.assertEqual(set(self.worker.data["rules"][0]["neighbors"]), set([2, 3]))

    def test_simple_rule_prepend_seq(self):
        self.assertEqual(
            set(self.worker.data["rules"][1]["prefixes"]),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )
        self.assertEqual(set(self.worker.data["rules"][1]["origin_asns"]), set([1]))
        self.assertEqual(self.worker.data["rules"][1]["prepend_seq"][0], [4, 3, 2])
        self.assertEqual(self.worker.data["rules"][1]["prepend_seq"][1], [8, 7, 6, 5])


if __name__ == "__main__":
    unittest.main()
