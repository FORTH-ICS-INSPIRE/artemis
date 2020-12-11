DROP VIEW view_hijacks;

ALTER TABLE hijacks
    ALTER COLUMN type TYPE VARCHAR ( 5 ) USING replace(replace(replace(replace(type::VARCHAR ( 1 ), 'S', 'S|-|-'), '0', 'E|0|-'), '1', 'E|1|-'), 'Q', 'Q|0|-')::VARCHAR ( 5 );

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, ignored, configured_prefix, comment, seen, withdrawn, outdated, peers_withdrawn, peers_seen FROM hijacks;
