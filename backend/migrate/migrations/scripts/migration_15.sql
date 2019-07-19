CREATE OR REPLACE VIEW view_index_all_stats
AS
SELECT stats.monitored_prefixes, stats.configured_prefixes,
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

DROP VIEW IF EXISTS view_stats;

CREATE FUNCTION search_bgpupdates_as_path(as_paths BIGINT[])
RETURNS SETOF view_bgpupdates AS $$
    SELECT *
    FROM view_bgpupdates
    WHERE
		as_paths <@ view_bgpupdates.as_path
$$ LANGUAGE sql STABLE;

CREATE FUNCTION search_bgpupdates_by_hijack_key(key text)
RETURNS SETOF view_bgpupdates AS $$
    SELECT *
    FROM view_bgpupdates
    WHERE
		key = ANY(view_bgpupdates.hijack_key)
$$ LANGUAGE sql STABLE;

CREATE FUNCTION search_bgpupdates_by_as_path_and_hijack_key(key text, as_paths BIGINT[])
	RETURNS SETOF view_bgpupdates AS $$
	SELECT *
	FROM view_bgpupdates
	WHERE
		key = ANY(view_bgpupdates.hijack_key) and as_paths <@ view_bgpupdates.as_path
$$ LANGUAGE sql STABLE;
