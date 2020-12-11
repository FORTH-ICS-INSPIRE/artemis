CREATE TABLE IF NOT EXISTS intended_process_states (
    name VARCHAR (32) UNIQUE,
    running BOOLEAN DEFAULT FALSE
);

CREATE OR REPLACE VIEW view_intended_process_states AS SELECT * FROM intended_process_states;
