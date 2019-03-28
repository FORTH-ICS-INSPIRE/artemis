DROP VIEW view_stats;

ALTER TABLE stats ADD COLUMN configured_prefixes BIGINT DEFAULT 0;

UPDATE stats SET monitored_prefixes=0, configured_prefixes=0;

CREATE OR REPLACE VIEW view_stats AS SELECT monitored_prefixes, configured_prefixes FROM stats;
