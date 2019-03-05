DROP VIEW view_configs;

ALTER TABLE configs DROP COLUMN config_data;

CREATE OR REPLACE VIEW view_configs AS SELECT raw_config, comment, time_modified FROM configs;
