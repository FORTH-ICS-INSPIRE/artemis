CREATE TABLE IF NOT EXISTS dataplane_msms (
    key VARCHAR ( 32 ) NOT NULL,
    hijack_key VARCHAR(32) NOT NULL,
    valid_origin_AS BIGINT,
    hijack_AS BIGINT,
    dst_addr inet,
    msm_type VARCHAR(10),
    msm_id BIGINT NOT NULL,
    msm_link text,
    responding VARCHAR(3) DEFAULT 'NA',
    hijacked VARCHAR(3) DEFAULT 'NA',
    PRIMARY KEY (key),
    UNIQUE (key, hijack_key, msm_id)
);

CREATE OR REPLACE VIEW view_dataplane_msms AS SELECT hijack_key, valid_origin_AS, hijack_AS, dst_addr, msm_type, msm_id, msm_link, responding, hijacked FROM dataplane_msms;
