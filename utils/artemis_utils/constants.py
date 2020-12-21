# constants (independent of environment)
import ujson as json


ASN_REGEX = r"^AS(\d+)$"
AUTOIGNORE_HOST = "autoignore"
BGPSTREAMHISTTAP_HOST = "bgpstreamhisttap"
BGPSTREAMKAFKATAP_HOST = "bgpstreamkafkatap"
BGPSTREAMLIVETAP_HOST = "bgpstreamlivetap"
CONFIGURATION_HOST = "configuration"
DATABASE_HOST = "database"
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
DETECTION_HOST = "detection"
EXABGPTAP_HOST = "exabgptap"
FILEOBSERVER_HOST = "fileobserver"
HEALTH_CHECK_TIMEOUT = 5
LOCALHOST = "127.0.0.1"
MAX_DATA_WORKER_WAIT_TIMEOUT = 10
MITIGATION_HOST = "mitigation"
NOTIFIER_HOST = "notifier"
PREFIXTREE_HOST = "prefixtree"
RIPE_ASSET_REGEX = r"^RIPE_WHOIS_AS_SET_(.*)$"
RIPERISTAP_HOST = "riperistap"
START_TIME_OFFSET = 3600
