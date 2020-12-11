DROP VIEW view_hijacks;

ALTER TABLE hijacks DROP CONSTRAINT possible_states;
ALTER TABLE hijacks ADD CONSTRAINT possible_states CHECK (
    (
        active=true and resolved=false and ignored=false and withdrawn=false and outdated=false
    ) or (
        active=false and resolved=true and ignored=false and withdrawn=false and outdated=false
    ) or (
        active=false and resolved=false and ignored=true and withdrawn=false and outdated=false
    ) or (
        active=false and resolved=false and ignored=false and withdrawn=false and outdated=true
    ) or (
        active=false and resolved=true and ignored=false and withdrawn=false and outdated=true
    ) or (
        active=false and resolved=false and ignored=true and withdrawn=false and outdated=true
    ) or (
        active=false and resolved=false and ignored=false and withdrawn=true and outdated=false
    ) or (
        active=false and resolved=false and ignored=false and withdrawn=true and outdated=true
    ) or (
        active=false and resolved=true and ignored=false and withdrawn=true and outdated=false
    ) or (
        active=false and resolved=false and ignored=true and withdrawn=true and outdated=false
    ) or (
        active=false and resolved=true and ignored=false and withdrawn=true and outdated=true
    ) or (
        active=false and resolved=false and ignored=true and withdrawn=true and outdated=true
    )
);

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, dormant, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen, outdated, community_annotation, rpki_status FROM hijacks;

DROP VIEW view_processes;

ALTER TABLE process_states ALTER COLUMN name TYPE VARCHAR (63);

CREATE OR REPLACE VIEW view_processes AS SELECT * FROM process_states;

DROP VIEW view_intended_process_states;

ALTER TABLE intended_process_states ALTER COLUMN name TYPE VARCHAR (63);

CREATE OR REPLACE VIEW view_intended_process_states AS SELECT * FROM intended_process_states;
