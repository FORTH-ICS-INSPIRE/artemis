DROP VIEW IF EXISTS view_dataplane_msms;
DROP TABLE IF EXISTS dataplane_msms;

CREATE TABLE IF NOT EXISTS dataplane_msms (
    key VARCHAR (32) NOT NULL,
    hijack_key VARCHAR(32) NOT NULL,
    msm_id BIGINT NOT NULL,
    msm_type VARCHAR(10),
    msm_protocol VARCHAR(4),
    msm_start_time TIMESTAMP,
    msm_stop_time TIMESTAMP,
    target_ip inet,
    num_of_probes BIGINT,
    hijacker_AS BIGINT,
    responding VARCHAR(3) DEFAULT 'NA',
    hijacked VARCHAR(3) DEFAULT 'NA',
    PRIMARY KEY (key),
    UNIQUE (key, hijack_key, msm_id)
);

CREATE OR REPLACE VIEW view_dataplane_msms AS SELECT hijack_key, msm_id, msm_type, msm_protocol, msm_start_time, msm_stop_time, target_ip, num_of_probes, hijacker_AS, responding, hijacked FROM dataplane_msms;
