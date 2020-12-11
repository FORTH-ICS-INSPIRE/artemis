DROP VIEW view_hijacks;

ALTER TABLE hijacks ADD COLUMN dormant BOOLEAN DEFAULT FALSE;
ALTER TABLE hijacks ADD CONSTRAINT dormant_active CHECK (
    (
        active=true and dormant=false
    ) or (
        active=true and dormant=true
    ) or (
        active=false and dormant=false
    )
);

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, dormant, ignored, configured_prefix, comment, seen, withdrawn, outdated, peers_withdrawn, peers_seen FROM hijacks;
