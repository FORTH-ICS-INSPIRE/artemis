DROP VIEW view_hijacks;

ALTER TABLE hijacks
    ADD COLUMN IF NOT EXISTS outdated BOOLEAN DEFAULT FALSE;

ALTER TABLE hijacks DROP CONSTRAINT possible_states;
ALTER TABLE hijacks ADD CONSTRAINT possible_states CHECK (
    (
        active=true and under_mitigation=false and resolved=false and ignored=false and withdrawn=false and outdated=false
    ) or (
        active=true and under_mitigation=true and resolved=false and ignored=false and withdrawn=false and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=true and ignored=false and withdrawn=false and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=true and withdrawn=false and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=false and withdrawn=false and outdated=true
    ) or (
        active=false and under_mitigation=false and resolved=true and ignored=false and withdrawn=false and outdated=true
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=true and withdrawn=false and outdated=true
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=false and withdrawn=true and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=false and withdrawn=true and outdated=true
    ) or (
        active=false and under_mitigation=false and resolved=true and ignored=false and withdrawn=true and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=true and withdrawn=true and outdated=false
    ) or (
        active=false and under_mitigation=false and resolved=true and ignored=false and withdrawn=true and outdated=true
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=true and withdrawn=true and outdated=true
    )
);


CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, ignored, configured_prefix, comment, seen, withdrawn, outdated, peers_withdrawn, peers_seen FROM hijacks;
