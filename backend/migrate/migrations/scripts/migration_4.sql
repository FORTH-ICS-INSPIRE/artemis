CREATE INDEX IF NOT EXISTS withdrawal_idx
ON bgp_updates(prefix, peer_asn, type, hijack_key);

CREATE INDEX IF NOT EXISTS handled_idx
ON bgp_updates(handled);

CREATE INDEX IF NOT EXISTS active_idx
ON hijacks(active);
