* **Prefix** (IPv4/IPv6):
  The IPv4/IPv6 prefix related to the BGP update or hijack
* **Origin AS**:
  The ASN of the AS that originated the BGP update
* **AS Path**:
  The AS-level path of the update. Empty for BGP withdrawals.
* **Peer AS**:
  The ASN of the monitor AS that peers with the route collector service reporting the BGP update.
* **Service**:
  Format <data_source> -> <other_info> -> <collector_name>. The route collector service that is connected to the monitor AS that observed the BGP update
* **Type**:
  A|W - Announcement|Withdrawal, respectively.
* **Timestamp**:
  The time when the BGP update was generated, as set by the BGP monitor or route collector service.
* **Hijack**:
  If present, redirects to a corresponding Hijack entry.
* **Status**:
  Blue "eye" if the detector has seen the BGP update and the update is already handled, grey if examination is pending. *Note that since ARTEMIS is a real-time system, if the detector is not active when the monitor captures and incoming BGP update, the update will never be handled in the future. If you need it handled you need to replay it from historical logs, "live" (with the detector active).
* Additional information under "More" tab:
  * **Communities**:
    Format [ASN:comm_id, ...]. BGP communities related to the BGP update.
  * **Original Path**:
    The original path of the BGP update. This is different from the reported AS Path only in the case where the BGP update is an announcement of a path containing AS-SETs of SEQUENCES, and the monitor microservice decomposes the update into multiple updates (with simple paths per update) for ease of interpretation and handling.
  * **Hijack Key**:
    Unique identifier/key of hijack event.
  * **Matched prefix**:
    The longest prefix that matched a rule in the configuration file. *Note that this might differ from the actually hijacked prefix contained in the BGP update in the case of a sub-prefix hijack event.*
  * **View Hijack**:
    Same as the "Hijack" field in the main table.
  * **Handled**:
    Same as the "Status" field in the main table.
