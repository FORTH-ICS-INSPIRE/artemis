CREATE OR REPLACE VIEW view_index_all_stats
AS
SELECT stats.monitored_prefixes, stats.configured_prefixes,
 	(SELECT count(*) Total_Hijacks FROM hijacks WHERE key is not NULL),
 	(SELECT count(*) Ignored_Hijacks FROM hijacks WHERE ignored = true),
 	(SELECT count(*) Resolved_Hijacks FROM hijacks WHERE resolved = true),
 	(SELECT count(*) Withdrawn_Hijacks FROM hijacks WHERE withdrawn = true),
 	(SELECT count(*) Mitigation_Hijacks FROM hijacks WHERE under_mitigation = true),
 	(SELECT count(*) Ongoing_Hijacks FROM hijacks WHERE active = true),
 	(SELECT count(*) Dormant_Hijacks FROM hijacks WHERE dormant = true),
 	(SELECT count(*) Acknowledged_Hijacks FROM hijacks WHERE seen = true),
 	(SELECT count(*) Outdated_Hijacks FROM hijacks WHERE outdated = true),
 	(SELECT count(*) Total_BGP_Updates FROM bgp_updates WHERE key is not NULL),
 	(SELECT count(*) Total_Unhandled_Updates FROM bgp_updates WHERE handled = false)
FROM stats;

DROP VIEW IF EXISTS view_stats;
