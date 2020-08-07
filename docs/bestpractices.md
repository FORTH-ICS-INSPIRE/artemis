## Location and Addressing

ARTEMIS is a locally deployed real-time BGP prefix hijacking monitoring, detection and mitigation tool.
When the IP address of the server on which ARTEMIS is running is affected by a hijack (e.g., routing to blackholes, etc.), the connectivity with the external (publicly available) monitors such as RIPE RIS, RouteViews and CAIDA BMP feeders might be hindered, rendering ARTEMIS "blind". We recommend the following countermeasures against this scenario:
1. Connect ARTEMIS also to a local monitor, using e.g., its exaBGP interface. This will ensure that even if the public monitors cannot be reached, information about BGP updates reaching your network will still reach ARTEMIS (for example, this might detect malicious BGP sub-prefix hijacks on the prefix where ARTEMIS itself is running).
2. Deploy redundant instances of ARTEMIS running in at least two different (disjoint) prefixes, to lower the probability of such an event happening.
3. Use private (or in general, internal) IPs for reaching ARTEMIS and connecting to a local monitor. The public-facing interfaces are primarily needed for communicating with external monitors, as well as serving the frontend content to ARTEMIS users.
4. Protect your ARTEMIS server with appropriate firewall rules. We never expose to the Internet what does not need to be exposed; opening port 443 for incoming HTTPS is typically the only actual requirement for ARTEMIS.

## Auto-cleaning

Use the `DB_AUTOCLEAN` env variable to automatically clean up benign BGP updates more than e.g., 24 hours old (units: hours), see [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/Environment-variables). This will also clean up unprocessed BGP updates that were generated from the monitor when the detector was OFF, or excess updates that arose during severe load periods and overwhelmed the detector.

## Excess load: Use multiple detectors/db access modules

See [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#invoking-multiple-detectorsdb-clients-optional). However pay also attention to the RAM requirements of the extra modules (see [here](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#memory-requirements))

## Dormant hijacks

By default ARTEMIS will consider all unresolved/unignored/non-withdrawn/non-outdated hijacks as "ongoing". You can set the `DB_HIJACK_DORMANT` flag; if an alert has not received BGP updates within the last `DB_HIJACK_DORMANT` hours, it will consider it as "dormant" and will restore it to fully ongoing if this changes.

## Custom logging

* You can set hijack logging filtering (depending on which communities are associated with the BGP hijack updates) using the `HIJACK_LOG_FILTER` env variable. For details, please check [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/Community-Annotations).
* You can select which fields of a hijack to log using the `HIJACK_LOG_FIELDS` env variable. The default fields are: `["prefix","hijack_as","type","time_started","time_last","peers_seen","configured_prefix","timestamp_of_config","asns_inf","time_detected","key","community_annotation","end_tag","hijack_url"]`.
* You can select the frequency of the alerts to see in the logging system by proper selection of the mail or hijack log handlers. Please check [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/ARTEMIS-logging).

## Configuration

Please check [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/Configuration-file).

## Kubernetes

We support Kubernetes besides docker-compose! Please check [this page](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/Kubernetes-Deployment).

## Connecting ARTEMIS frontend to LDAP

Please check instructions [here](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/LDAP).
