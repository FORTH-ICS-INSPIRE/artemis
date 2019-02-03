DROP VIEW view_configs;

CREATE OR REPLACE VIEW view_configs AS SELECT raw_config, comment, time_modified FROM configs;

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
