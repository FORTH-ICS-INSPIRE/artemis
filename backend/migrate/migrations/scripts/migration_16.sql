DROP VIEW view_index_all_stats;

ALTER TABLE stats ADD COLUMN monitor_peers BIGINT NOT NULL DEFAULT 0;

UPDATE stats SET monitored_prefixes=0, configured_prefixes=0, monitor_peers=0;

CREATE OR REPLACE VIEW view_index_all_stats
AS
SELECT stats.monitored_prefixes, stats.configured_prefixes, stats.monitor_peers,
    (SELECT count(*) total_hijacks FROM hijacks WHERE key is not NULL),
    (SELECT count(*) ignored_hijacks FROM hijacks WHERE ignored = true),
    (SELECT count(*) resolved_hijacks FROM hijacks WHERE resolved = true),
    (SELECT count(*) withdrawn_hijacks FROM hijacks WHERE withdrawn = true),
    (SELECT count(*) mitigation_hijacks FROM hijacks WHERE under_mitigation = true),
    (SELECT count(*) ongoing_hijacks FROM hijacks WHERE active = true),
    (SELECT count(*) dormant_hijacks FROM hijacks WHERE dormant = true),
    (SELECT count(*) acknowledged_hijacks FROM hijacks WHERE seen = true),
    (SELECT count(*) outdated_hijacks FROM hijacks WHERE outdated = true),
    (SELECT count(*) total_bgp_updates FROM bgp_updates WHERE key is not NULL),
    (SELECT count(*) total_unhandled_updates FROM bgp_updates WHERE handled = false)
FROM stats;
