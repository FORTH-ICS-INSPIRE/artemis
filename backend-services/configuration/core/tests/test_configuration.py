import unittest
from unittest.mock import mock_open
from unittest.mock import patch

import configuration

TEST_CONF_DATA = """
prefixes:
    prefix_1: &prefix_1
    - 10.0.0.0/8
    - 10.1.0.0/16
monitors:
    riperis: [''] # by default this uses all available monitors
    bgpstreamlive:
    - routeviews
    - ris
    exabgp:
    - ip: exabgp # this will automatically be resolved to the exabgp container's IP
      port: 5000 # default port
      autoconf: "true"
      learn_neighbors: "true"
    bgpstreamkafka:
        host: bmp.bgpstream.caida.org
        port: 9092
        topic: '^openbmp.router--.+.peer-as--.+.bmp_raw'
    bgpstreamhist: "./"
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
    def setUp(self) -> None:
        self.configurationService = configuration.Configuration()
        # reads and parses initial configuration file
        with open(
            self.configurationService.shared_memory_manager_dict["config_file"], "r"
        ) as f:
            raw = f.read()
            (
                self.configurationService.shared_memory_manager_dict["config_data"],
                _flag,
                _error,
            ) = configuration.parse(raw, yaml=True)

    def test_prefixes(self):
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "prefixes"
                ]["prefix_1"]
            ),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )

    def test_monitors(self):
        self.assertTrue(
            "riperis"
            in self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]
        )

        self.assertTrue(
            "bgpstreamlive"
            in self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]
        )

        self.assertTrue(
            "bgpstreamkafka"
            in self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["bgpstreamkafka"]["host"],
            "bmp.bgpstream.caida.org",
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["bgpstreamkafka"]["port"],
            9092,
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["bgpstreamkafka"]["topic"],
            "^openbmp.router--.+.peer-as--.+.bmp_raw",
        )

        self.assertTrue(
            "exabgp"
            in self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["exabgp"][0]["ip"],
            "exabgp",
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["exabgp"][0]["port"],
            5000,
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["exabgp"][0]["autoconf"],
            True,
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["exabgp"][0]["learn_neighbors"],
            True,
        )

        self.assertTrue(
            "bgpstreamhist"
            in self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "monitors"
            ]["bgpstreamhist"],
            "./",
        )

    def test_asns(self):
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "asns"
                ]["origins"]
            ),
            set([1]),
        )
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "asns"
                ]["neighbors"]
            ),
            set([2, 3]),
        )

    def test_simple_rule_neighbors(self):
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "rules"
                ][0]["prefixes"]
            ),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "rules"
                ][0]["origin_asns"]
            ),
            set([1]),
        )
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "rules"
                ][0]["neighbors"]
            ),
            set([2, 3]),
        )

    def test_simple_rule_prepend_seq(self):
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "rules"
                ][1]["prefixes"]
            ),
            set(["10.0.0.0/8", "10.1.0.0/16"]),
        )
        self.assertEqual(
            set(
                self.configurationService.shared_memory_manager_dict["config_data"][
                    "rules"
                ][1]["origin_asns"]
            ),
            set([1]),
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "rules"
            ][1]["prepend_seq"][0],
            [4, 3, 2],
        )
        self.assertEqual(
            self.configurationService.shared_memory_manager_dict["config_data"][
                "rules"
            ][1]["prepend_seq"][1],
            [8, 7, 6, 5],
        )


if __name__ == "__main__":
    unittest.main()
