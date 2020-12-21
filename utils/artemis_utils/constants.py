# constants (independent of environment)
import ujson as json

ASN_REGEX = r"^AS(\d+)$"
DEFAULT_HIJACK_LOG_FIELDS = json.dumps(
    [
        "prefix",
        "hijack_as",
        "type",
        "time_started",
        "time_last",
        "peers_seen",
        "configured_prefix",
        "timestamp_of_config",
        "asns_inf",
        "time_detected",
        "key",
        "community_annotation",
        "rpki_status",
        "end_tag",
        "outdated_parent",
        "hijack_url",
    ]
)
DEFAULT_MON_TIMEOUT_LAST_BGP_UPDATE = 60 * 60
RIPE_ASSET_REGEX = r"^RIPE_WHOIS_AS_SET_(.*)$"
