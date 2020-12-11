DROP VIEW view_stats;

ALTER TABLE stats ALTER COLUMN monitored_prefixes SET NOT NULL;
ALTER TABLE stats ADD COLUMN configured_prefixes BIGINT NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS stats_one_row
ON stats((monitored_prefixes IS NOT NULL));

CREATE OR REPLACE FUNCTION stats_no_delete ()
RETURNS trigger
LANGUAGE plpgsql AS $f$
BEGIN
   RAISE EXCEPTION 'You may not delete the stats!';
END; $f$;

CREATE TRIGGER stats_no_delete
BEFORE DELETE ON stats
FOR EACH ROW EXECUTE PROCEDURE stats_no_delete();

UPDATE stats SET monitored_prefixes=0, configured_prefixes=0;

CREATE OR REPLACE VIEW view_stats AS SELECT monitored_prefixes, configured_prefixes FROM stats;
