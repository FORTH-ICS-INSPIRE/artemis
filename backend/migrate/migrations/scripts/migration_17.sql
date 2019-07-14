DROP VIEW view_hijacks;

ALTER TABLE hijacks ADD COLUMN community_annotation text DEFAULT 'NA';

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, dormant, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen, outdated, community_annotation FROM hijacks;
