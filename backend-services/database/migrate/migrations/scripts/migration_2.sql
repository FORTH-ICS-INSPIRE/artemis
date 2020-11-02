DROP VIEW view_hijacks;
DROP VIEW view_bgpupdates;

ALTER TABLE bgp_updates
    ALTER COLUMN as_path TYPE BIGINT[] USING as_path::BIGINT[],
    ALTER hijack_key TYPE text[] USING array[hijack_key];

ALTER TABLE hijacks
    ADD COLUMN withdrawn BOOLEAN DEFAULT FALSE,
    ADD COLUMN peers_withdrawn BIGINT[] DEFAULT array[]::BIGINT[],
    ALTER COLUMN peers_seen TYPE BIGINT[] USING translate(peers_seen::text, '[]','{}')::BIGINT[],
    ALTER COLUMN asns_inf TYPE BIGINT[] USING translate(asns_inf::text, '[]','{}')::BIGINT[];


ALTER TABLE hijacks DROP CONSTRAINT possible_states;
ALTER TABLE hijacks ADD CONSTRAINT possible_states CHECK (
    (
        active=true and under_mitigation=false and resolved=false and ignored=false and withdrawn=false
    ) or (
        active=true and under_mitigation=true and resolved=false and ignored=false and withdrawn=false
    ) or (
        active=false and under_mitigation=false and resolved=true and ignored=false and withdrawn=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=true and withdrawn=false
    ) or (
        active=false and under_mitigation=false and resolved=false and ignored=false and withdrawn=true
    )
);


CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen FROM hijacks;

CREATE OR REPLACE VIEW view_bgpupdates AS SELECT prefix, origin_as, peer_asn, as_path, service, type, communities, timestamp, hijack_key, handled, matched_prefix, orig_path FROM bgp_updates;
