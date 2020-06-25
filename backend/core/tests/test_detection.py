import logging
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

logging.disable(logging.CRITICAL)

import detection


class BGPHandlerTester(unittest.TestCase):
    """
    Detection combinations to check:
    S|0|-|-: sub-prefix announced by illegal origin
    S|0|-|L: sub-prefix announced by illegal origin and no-export policy violation
    S|1|-|-: sub-prefix announced by seemingly legal origin, but with an illegal first hop
    S|1|-|L: sub-prefix announced by seemingly legal origin, but with an illegal first hop and no-export policy violation
    S|-|-|-: not S|0|- or S|1|-, potential type-N or type-U hijack
    S|-|-|L: not S|0|- or S|1|-, potential type-N or type-U hijack and no-export policy violation
    E|0|-|-: exact-prefix announced by illegal origin
    E|0|-|-|L: exact-prefix announced by illegal origin and no-export policy violation
    E|1|-|-: exact-prefix announced by seemingly legal origin, but with an illegal first hop
    E|1|-|L: exact-prefix announced by seemingly legal origin, but with an illegal first hop and no-export policy violation
    Q|0|-|-: squatting hijack (is always '0' on the path dimension since any origin is illegal)
    Q|0|-|L: squatting hijack and no-export policy violation
    E|-|-|-: not a hijack
    E|-|-|L: no-export policy violation
    """

    @patch("redis.Redis", MagicMock())
    @patch("detection.signal_loading", MagicMock())
    @patch("detection.ping_redis", MagicMock())
    @patch("detection.Detection.Worker.config_request_rpc", MagicMock())
    def setUp(self) -> None:
        self.worker = detection.Detection.Worker(MagicMock())
        self.worker.rules = [
            {
                "prefixes": ["10.0.0.0/24"],
                "origin_asns": [1],
                "neighbors": [2],
                "mitigation": ["manual"],
                "policies": [],
                "community_annotations": [],
            },
            {
                "prefixes": ["9.0.5.0/24"],
                "origin_asns": [245],
                "neighbors": [-1],
                "policies": ["no-export"],
                "mitigation": ["manual"],
                "community_annotations": [],
            },
            {
                "prefixes": ["9.0.6.0/24"],
                "origin_asns": [245],
                "neighbors": [2],
                "policies": ["no-export"],
                "mitigation": ["manual"],
                "community_annotations": [],
            },
            {
                "prefixes": ["8.0.0.0/24"],
                "origin_asns": [],
                "neighbors": [],
                "policies": [],
                "mitigation": ["manual"],
                "community_annotations": [],
            },
            {
                "prefixes": ["7.0.0.0/24"],
                "origin_asns": [],
                "neighbors": [],
                "policies": ["no-export"],
                "mitigation": ["manual"],
                "community_annotations": [],
            },
        ]
        self.worker.init_detection()

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_0(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 100],
            "prefix": "10.0.0.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 100)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "0", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_0_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 100],
            "prefix": "9.0.5.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 100)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "0", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_1(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 1],
            "prefix": "10.0.0.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 200)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "1", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_1_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 245],
            "prefix": "9.0.6.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 200)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "1", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_N(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 1],
            "prefix": "10.0.0.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], -1)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "-", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_subprefix_type_N_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 245],
            "prefix": "9.0.6.0/25",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 2)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["S", "-", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_exact_type_0(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 100],
            "prefix": "10.0.0.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 100)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["E", "0", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_exact_type_0_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 1],
            "prefix": "9.0.5.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 1)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["E", "0", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_exact_type_1(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 1],
            "prefix": "10.0.0.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 200)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["E", "1", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_exact_type_1_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 245],
            "prefix": "9.0.6.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 200)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["E", "1", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_squatting(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 245],
            "prefix": "8.0.0.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 245)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["Q", "0", "-", "-"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_squatting_no_export(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 200, 245],
            "prefix": "7.0.0.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertTrue(mock_commit_hijack.called)
        self.assertEqual(mock_commit_hijack.call_args[0][1], 245)
        self.assertEqual(mock_commit_hijack.call_args[0][2], ["Q", "0", "-", "L"])

    @patch("detection.Detection.Worker.commit_hijack")
    def test_handle_bgp_update_no_hijack(self, mock_commit_hijack):
        message = {
            "key": "1",
            "timestamp": 1,
            "orig_path": [],
            "communities": [],
            "service": "a",
            "type": "A",
            "path": [4, 3, 2, 1],
            "prefix": "10.0.0.0/24",
            "peer_asn": 4,
        }
        self.worker.handle_bgp_update(message)

        self.assertFalse(mock_commit_hijack.called)


if __name__ == "__main__":
    unittest.main()
