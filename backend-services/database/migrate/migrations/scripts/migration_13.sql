CREATE TABLE IF NOT EXISTS stats (
    monitored_prefixes BIGINT DEFAULT 0
);

INSERT INTO stats (monitored_prefixes) VALUES (0);

CREATE OR REPLACE VIEW view_stats AS SELECT monitored_prefixes FROM stats;
