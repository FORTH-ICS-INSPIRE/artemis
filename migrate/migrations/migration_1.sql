CREATE TABLE IF NOT EXISTS db_details (
id INTEGER GENERATED ALWAYS AS IDENTITY,
version BIGINT DEFAULT FALSE);


ALTER TABLE hijacks
ADD COLUMN seen BOOLEAN DEFAULT FALSE;


CREATE OR REPLACE VIEW view_hijacks AS SELECT 
key,type, prefix, hijack_as, num_peers_seen, 
num_asns_inf, time_started, time_ended, time_last, 
mitigation_started, time_detected, timestamp_of_config, 
under_mitigation, resolved, active, ignored, configured_prefix, 
comment, seen FROM hijacks;