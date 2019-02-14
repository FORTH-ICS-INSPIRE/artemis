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

INSERT INTO db_details (version, upgraded_on) VALUES (7, now());

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

create trigger send_update_event
after insert on bgp_updates
for each row execute procedure rabbitmq.on_row_change();

CREATE TABLE IF NOT EXISTS hijacks (
    key VARCHAR ( 32 ) NOT NULL,
    type  VARCHAR ( 5 ),
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
    configured_prefix  inet,
    timestamp_of_config TIMESTAMP,
    comment text,
    seen BOOLEAN DEFAULT FALSE,
    PRIMARY KEY(time_detected, key),
    UNIQUE(time_detected, key),
    CONSTRAINT possible_states CHECK (
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
    )
);

CREATE INDEX active_idx
ON hijacks(active);

SELECT create_hypertable('hijacks', 'time_detected', if_not_exists => TRUE);

-- create trigger send_hijack_event
-- after insert or update or delete on hijacks
-- for each row execute procedure rabbitmq.on_row_change("hijack");

CREATE TABLE IF NOT EXISTS configs (
    key VARCHAR ( 32 ) NOT NULL,
    config_data  json,
    raw_config  text,
    comment text,
    time_modified TIMESTAMP NOT NULL
);

CREATE OR REPLACE VIEW view_configs AS SELECT raw_config, comment, time_modified FROM configs;

CREATE OR REPLACE VIEW view_hijacks AS SELECT key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen, outdated FROM hijacks;

CREATE OR REPLACE VIEW view_bgpupdates AS SELECT prefix, origin_as, peer_asn, as_path, service, type, communities, timestamp, hijack_key, handled, matched_prefix, orig_path FROM bgp_updates;

CREATE OR REPLACE FUNCTION inet_search (inet)
RETURNS SETOF bgp_updates AS $$
SELECT * FROM bgp_updates WHERE prefix << $1;
$$ LANGUAGE SQL;

CREATE TABLE IF NOT EXISTS process_states (
    name VARCHAR (32) UNIQUE,
    running BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP default current_timestamp
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
