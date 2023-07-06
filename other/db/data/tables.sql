CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE TABLE IF NOT EXISTS db_details (
version BIGINT NOT NULL,
upgraded_on TIMESTAMPTZ NOT NULL);

CREATE UNIQUE INDEX db_details_one_row
ON db_details((version IS NOT NULL));

CREATE FUNCTION db_version_no_delete ()
RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
   RAISE EXCEPTION 'You may not delete the db_details!';
END; $f$;

CREATE FUNCTION array_distinct(anyarray) RETURNS anyarray AS $f$
  SELECT array_agg(DISTINCT x) FROM unnest($1) t(x);
$f$ LANGUAGE SQL IMMUTABLE;

CREATE TRIGGER db_details_no_delete
BEFORE DELETE ON db_details
FOR EACH ROW EXECUTE PROCEDURE db_version_no_delete();

INSERT INTO db_details (version, upgraded_on) VALUES (24, now());

CREATE TABLE IF NOT EXISTS bgp_updates (
    key VARCHAR ( 32 ) NOT NULL,
    prefix inet,
    origin_as BIGINT,
    peer_asn   BIGINT,
    as_path   BIGINT[],
    service   VARCHAR ( 50 ),
    type  VARCHAR ( 1 ),
    communities  json,
    timestamp TIMESTAMP  NOT NULL,
    hijack_key text[],
    handled   BOOLEAN,
    matched_prefix inet,
    orig_path json,
    PRIMARY KEY(timestamp, key),
    UNIQUE(timestamp, key)
);

CREATE INDEX withdrawal_idx
ON bgp_updates(prefix, peer_asn, type, hijack_key);

CREATE INDEX handled_idx
ON bgp_updates(handled);

SELECT create_hypertable('bgp_updates', 'timestamp', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS hijacks (
    key VARCHAR ( 32 ) NOT NULL,
    type  VARCHAR ( 7 ),
    prefix inet,
    hijack_as BIGINT,
    peers_seen   BIGINT[],
    peers_withdrawn BIGINT[],
    num_peers_seen INTEGER,
    asns_inf BIGINT[],
    num_asns_inf INTEGER,
    time_started TIMESTAMP,
    time_last TIMESTAMP,
    time_ended   TIMESTAMP,
    mitigation_started   TIMESTAMP,
    time_detected TIMESTAMP  NOT NULL,
    under_mitigation BOOLEAN,
    resolved  BOOLEAN,
    active  BOOLEAN,
    ignored BOOLEAN,
    withdrawn BOOLEAN,
    outdated BOOLEAN DEFAULT FALSE,
    dormant BOOLEAN DEFAULT FALSE,
    configured_prefix  inet,
    timestamp_of_config TIMESTAMP,
    comment text,
    seen BOOLEAN DEFAULT FALSE,
    community_annotation text DEFAULT 'NA',
    rpki_status VARCHAR ( 2 ) DEFAULT 'NA',
    PRIMARY KEY(time_detected, key),
    UNIQUE(time_detected, key),
    CONSTRAINT possible_states CHECK (
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
    ),
    CONSTRAINT dormant_active CHECK (
        (
            active=true and dormant=false
        ) or (
            active=true and dormant=true
        ) or (
            active=false and dormant=false
        )
    )
);

CREATE INDEX active_idx
ON hijacks(active);

CREATE INDEX hijack_table_idx
ON hijacks(time_last, hijack_as, prefix, type);

SELECT create_hypertable('hijacks', 'time_detected', if_not_exists => TRUE);

-- create trigger send_hijack_event
-- after insert or update or delete on hijacks
-- for each row execute procedure rabbitmq.on_row_change("hijack");

CREATE TABLE IF NOT EXISTS configs (
    key VARCHAR ( 32 ) NOT NULL,
    raw_config  text,
    comment text,
    time_modified TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS stats (
    monitored_prefixes BIGINT NOT NULL DEFAULT 0,
    configured_prefixes BIGINT NOT NULL DEFAULT 0,
    monitor_peers BIGINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX stats_one_row
ON stats((monitored_prefixes IS NOT NULL));

CREATE FUNCTION stats_no_delete ()
RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
   RAISE EXCEPTION 'You may not delete the stats!';
END; $f$;

CREATE TRIGGER stats_no_delete
BEFORE DELETE ON stats
FOR EACH ROW EXECUTE PROCEDURE stats_no_delete();

INSERT INTO stats (monitored_prefixes, configured_prefixes, monitor_peers) VALUES (0, 0, 0);

CREATE OR REPLACE VIEW view_configs AS SELECT raw_config, comment, time_modified FROM configs;

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, dormant, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen, outdated, community_annotation, rpki_status FROM hijacks;

CREATE OR REPLACE VIEW view_bgpupdates AS SELECT prefix, origin_as, peer_asn, as_path, service, type, communities, timestamp, hijack_key, handled, matched_prefix, orig_path FROM bgp_updates;

CREATE OR REPLACE VIEW view_index_all_stats
AS
SELECT stats.monitored_prefixes, stats.configured_prefixes, stats.monitor_peers,
    (SELECT count(*) total_hijacks FROM hijacks WHERE key is not NULL),
    (SELECT count(*) ignored_hijacks FROM hijacks WHERE ignored = true),
    (SELECT count(*) resolved_hijacks FROM hijacks WHERE resolved = true),
    (SELECT count(*) withdrawn_hijacks FROM hijacks WHERE withdrawn = true),
    (SELECT count(*) mitigation_hijacks FROM hijacks WHERE under_mitigation = true),
    (SELECT count(*) ongoing_hijacks FROM hijacks WHERE active = true),
    (SELECT count(*) dormant_hijacks FROM hijacks WHERE dormant = true),
    (SELECT count(*) acknowledged_hijacks FROM hijacks WHERE seen = true),
    (SELECT count(*) outdated_hijacks FROM hijacks WHERE outdated = true),
    (SELECT count(*) total_bgp_updates FROM bgp_updates WHERE key is not NULL),
    (SELECT count(*) total_unhandled_updates FROM bgp_updates WHERE handled = false)
FROM stats;

CREATE OR REPLACE FUNCTION inet_search (inet)
RETURNS SETOF bgp_updates AS $$
SELECT * FROM bgp_updates WHERE prefix << $1;
$$ LANGUAGE SQL;

CREATE TABLE IF NOT EXISTS process_states (
    name VARCHAR (63) UNIQUE,
    running BOOLEAN DEFAULT FALSE,
    loading BOOLEAN DEFAULT FALSE,
    extra_info VARCHAR (63) DEFAULT '',
    timestamp TIMESTAMP default current_timestamp
);

CREATE TABLE IF NOT EXISTS intended_process_states (
    name VARCHAR (63) UNIQUE,
    extra_info VARCHAR (63) DEFAULT '',
    running BOOLEAN DEFAULT FALSE
);

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.timestamp = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_process_timestamp
BEFORE UPDATE ON process_states
FOR EACH ROW EXECUTE PROCEDURE update_timestamp();

CREATE OR REPLACE VIEW view_processes AS SELECT * FROM process_states;

CREATE OR REPLACE VIEW view_intended_process_states AS SELECT * FROM intended_process_states;

CREATE OR REPLACE VIEW view_db_details AS SELECT version, upgraded_on FROM db_details;

CREATE FUNCTION search_bgpupdates_as_path(as_paths BIGINT[])
RETURNS SETOF view_bgpupdates AS $$
    SELECT *
    FROM view_bgpupdates
    WHERE
        as_paths <@ view_bgpupdates.as_path
$$ LANGUAGE sql STABLE;

CREATE FUNCTION search_bgpupdates_by_hijack_key(key text)
RETURNS SETOF view_bgpupdates AS $$
    SELECT *
    FROM view_bgpupdates
    WHERE
        key = ANY(view_bgpupdates.hijack_key)
$$ LANGUAGE sql STABLE;

CREATE FUNCTION search_bgpupdates_by_as_path_and_hijack_key(key text, as_paths BIGINT[])
    RETURNS SETOF view_bgpupdates AS $$
    SELECT *
    FROM view_bgpupdates
    WHERE
        key = ANY(view_bgpupdates.hijack_key) and as_paths <@ view_bgpupdates.as_path
$$ LANGUAGE sql STABLE;

CREATE TABLE IF NOT EXISTS dataplane_msms (
    key VARCHAR (32) NOT NULL,
    hijack_key VARCHAR(32) NOT NULL,
    msm_id BIGINT NOT NULL,
    msm_type VARCHAR(10),
    msm_protocol VARCHAR(4),
    msm_start_time TIMESTAMP,
    msm_stop_time TIMESTAMP,
    target_ip inet,
    num_of_probes BIGINT,
    hijacker_AS BIGINT,
    responding VARCHAR(3) DEFAULT 'NA',
    hijacked VARCHAR(3) DEFAULT 'NA',
    PRIMARY KEY (key),
    UNIQUE (key, hijack_key, msm_id)
);

CREATE OR REPLACE VIEW view_dataplane_msms AS SELECT hijack_key, msm_id, msm_type, msm_protocol, msm_start_time, msm_stop_time, target_ip, num_of_probes, hijacker_AS, responding, hijacked FROM dataplane_msms;
