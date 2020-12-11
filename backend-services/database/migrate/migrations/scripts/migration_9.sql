DROP VIEW view_hijacks;

ALTER TABLE hijacks
    ALTER COLUMN type TYPE VARCHAR ( 7 ) USING replace(
    replace(
    replace(
    replace(
    replace(
    replace(type::VARCHAR ( 5 ), 'S|0|-', 'S|0|-|-'),
    'S|1|-', 'S|1|-|-'),
    'S|-|-', 'S|-|-|-'),
    'E|0|-', 'E|0|-|-'),
    'E|1|-', 'E|1|-|-'),
    'Q|0|-', 'Q|0|-|-')::VARCHAR ( 7 );

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, ignored, configured_prefix, comment, seen, withdrawn, outdated, peers_withdrawn, peers_seen FROM hijacks;
