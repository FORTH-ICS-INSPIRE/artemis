# Changelog

## [UNRELEASED] - YYYY-MM-DD
### Added (BASIC ARTEMIS ARCHITECTURE)
- Real-time monitoring of the changes in the BGP routes of the network's prefixes.
ARTEMIS connects and receives real-time feeds of BGP updates from the streaming
BGP route collectors of [RIPE RIS](http://stream-dev.ris.ripe.net/demo) and
[BGPStream](https://bgpstream.caida.org/) (RouteViews + RIPE RIS).
Optionally, it connects to and receives BGP information from local routers through
[exaBGP](https://github.com/Exa-Networks/exabgp).
- Real-time detection of BGP prefix hijacking attacks/events of the following types:
exact-prefix type-0/1, sub-prefix of any type, and squatting attacks.
- Manual mitigation of BGP prefix hijacking attacks. Upon the detection of a
suspicious event (potential hijack), the network operator is immediately
sent a notification (e.g., UI entry or email) detailing the following information:
```
{
'prefix': ...,
'hijacker_AS': ...,
'hijack_type':...,
'time_detected':...,
'time_started': ...,
'time_last_updated': ...,
'peers_seen': ...,
'inf_asns': ...
}
```
and ARTEMIS offers the option to run a custom script defined by the operator.
- Web interface used by the network administrator to:
(i) provide configuration
information (ASNs, prefixes, routing policies, etc.) via a web form or text editor,
(ii) control ARTEMIS modules (start/stop/status),
(iii) monitor in real-time the BGP state related to the IP prefixes of interest,
(iv) view details of BGP hijacks of monitored prefixes,
(v) monitor in real-time the status of ongoing, unresolved BGP hijacks,
(vi) press button to trigger a custom mitigation process, mark as manually mitigated ("resolve")
or ignore the event as a false positive,
(vii) register and manage users (ADMIN|VIEWER).
- Configuration file editable by the operator (directly or via the web interface),
containing information about: prefixes, ASNs, monitors and ARTEMIS rules ("ASX advertises prefix P to ASY").
- CLI to start/stop ARTEMIS modules and query their status (running state, uptime).
- Support for both IPv4 and IPv6 prefixes.

# SAMPLE
## [RELEASE_VERSION] - YEAR-MONTH-DAY
### Added
- TBD (Added a new feature)

### Changed
- TBD (Changed existing functionality)

### Fixed
- TBD (bug-fix)

### Removed
- TBD (removed a feature)

### Deprecated
- TBD (soon-to-be removed feature)

### Security
- TBD (addressing vulnerability)

## ACKS
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

