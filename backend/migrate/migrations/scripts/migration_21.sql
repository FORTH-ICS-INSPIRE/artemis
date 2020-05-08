DROP VIEW view_processes;

ALTER TABLE process_states ADD COLUMN loading BOOLEAN DEFAULT FALSE;

CREATE OR REPLACE VIEW view_processes AS SELECT * FROM process_states;
