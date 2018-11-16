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

CREATE TRIGGER db_details_no_delete
BEFORE DELETE ON db_details
FOR EACH ROW EXECUTE PROCEDURE db_version_no_delete();

INSERT INTO db_details (version, upgraded_on) VALUES (0, now());

ALTER TABLE hijacks
ADD COLUMN seen BOOLEAN DEFAULT FALSE;

CREATE OR REPLACE VIEW view_hijacks AS SELECT
key,type, prefix, hijack_as, num_peers_seen,
num_asns_inf, time_started, time_ended, time_last,
mitigation_started, time_detected, timestamp_of_config,
under_mitigation, resolved, active, ignored, configured_prefix,
comment, seen FROM hijacks;
