# Changelog

## [UNRELEASED] (NAME) - YYYY-MM-DD
### Added
- Slack logging package and example

### Changed
- Refactoring frontend (views, templates and static files are organized inside the folder render)
- Update hasura (1.0.0alpha42 -> 1.0.0alpha45)
- ARTEMIS logo

### Fixed
- TBD (bug-fix)

### Removed
- TBD (removed a feature)

### Deprecated
- TBD (soon-to-be removed feature)

### Security
- Bumped SQLAlchemy from 1.2.16 to 1.3.3 in /frontend

## [1.2.0] (Athena) - 2019-04-10
### Added
- Support for dormant flags in hijacks
- Storing hijack update (origin, neighbor) combinations in redis
- Translate learn rule request in ARTEMIS-compatible dicts in backend
- Translate learn rule ARTEMIS-compatible dicts into yaml conf in backend
- Update yaml conf with learned rule
- Learn rule action for ongoing hijacks in frontend after ignore action
- Configured/matched prefix field and search in frontend hijack and update tables
- Monitored prefixes count in stats table (overview)
- Configured prefixes count in stats table (overview)
- Initial kubernetes/helm (helm-charts) support
- Reject old updates from taps and have a "HISTORIC" variable to enable/disable
- Initial support for LDAP authentication
- Delete hijack functionality
- Abuse contact details for each ASN (Extracted from RIPEStat)
- Functionality to copy ASN details on clickboard
- Support to filter BGP Updates based on their AS Path
- Display distinct values of BGP Updates for the following fields: "Origin AS", "Peer AS" and "service" in hijack view

### Changed
- Using prefix lists in json file format as monitoring taps input to avoid problematic ultra long arguments
- Refactored environment variables
- Use of RIPE RIS firehose stream instead of the websocket clientui8
- Use of function url_for in flask redirect
- In hijack view changed the actions functionality
- Update hasura (1.0.0alpha31 -> 1.0.0alpha42)
- Hijack view now uses hasura graphql to fetch BGP Updates

### Fixed
- Correct RFC2622 translation when needed in frontend and backend
- When learning ignore rule, escape special character ":" (IPv6)
- Problematic start of RIS and exaBGP monitors, even if not configured
- BGP update redis bootstraping from DB
- UI support for multiple instances of a module in overview and system page
- Bug with hijack view times
- Bug with hijack view action buttons

### Removed
- Configured prefix graph visualization (needs redesign)
- Config data field from configs DB table

### Security
- Using yaml dump and safe_load instead of pickling/unpickling

## [1.1.1] (Atlas) - 2019-02-28
### Added
- Tooltip support for peers seen BGP Announcement/Withdrawal on hijack view.
- Support for rfc2622 ^+, ^-, ^n and ^n-m prefix operators in configuration
- More tests for checking withdrawn hijacks
- Coverage tests for frontend actions
- Pre-commit hooks
- Policy dimension on hijacks (route leak detection based on no-export)
- Support for auto-cleaning unneeded BGP updates
- Automated DB backups
- View hijack by key
- Enable sorting for columns: # Peers Seen/# ASes Infected
- Added DB version on overview page

### Changed
- Testing refactoring
- RIPE RIS live python websocket client

### Fixed
- Updated/optimized db query for removing withdrawn peers (newer announcement)
- Support for different user/pass on rabbitmq
- Solved bug with randomized config hashing
- Fixed expected behavior when trying to run old containers on new DBs

### Deprecated
- Backup files

## [1.1.0] (Asclepius) - 2019-02-20
### Added
- Bug report and feature request issue templates
- Code of conduct
- CI/CD container
- SemaphoreCI testing for backend
- Automation of system and DB migration
- Multi-process Database support through supervisor
- Custom monitor for high-throughput measuring (taps/custom.py)
- Instructions on local configuration decoupling
- Support for wildcards (origin_asns, neighbors) in configuration
- Enabled POST request on /jwt/auth to retrieve authentication token

### Changed
- Done misc updates on README
- Moved static js libraries to CDN
- Upgraded requirements in frontend
- Upgraded requirements in backend
- Display tooltip for hijack ASN in hijack view page
- Display tooltip for monitors in BGP Updates table in hijack view page
- Updated default and sample configuration files in backend/configs
- Moved js minifier to container builder
- Revised detection logic to account for hijack dimensions
- Using the Seen/Acknowledged to confirm true or false hijack

### Fixed
- Misc code quality improvements
- Fetch API support for older browsers
- UI fixes (Hijack->Hijacker)
- Fix indentation on hijacks table
- Make more clear the buttons of navbar
- Change Timewindow phrase on BGP Updates and Hijacks tables
- Bug with custom window
- Update Hijack tags filter
- Add 'Last Update' on hijacks tables
- Optimizations in file: display_info.js

### Removed
- ACKS file (moved to README in-line)

### Deprecated
- Removed deprecated graphql query
- "Migrate" container (functionality integrated in backend)

### Security
- Bumped flask from 0.12.2 to 1.0.2 in /frontend
- Bumped requests from 2.19.1 to 2.21.0 in /frontend
- Bumped PyYAML from 3.13 to 4.2b4 in /frontend
- Bumped PyYAML from 3.13 to 4.2b4 in /backend
- Resolved bug with user roles on registration process

## [1.0.0] (Apollo) - 2018-12-20
### Added
* Monitor micro-service, providing real-time monitoring of the changes in the BGP routes of the network's prefixes.
Support for the following route collectors and interfaces:
  * [RIPE RIS](http://stream-dev.ris.ripe.net/demo2) (real-time streaming)
  * [BGPStream](https://bgpstream.caida.org/), supporting:
    * RouteViews and RIPE RIS (30-minute delayed streaming)
    * BetaBMP (real-time streaming)
    * Historical updates replayed from csv files (historical streaming)
  * [exaBGP](https://github.com/Exa-Networks/exabgp) (real-time streaming)
* Configuration micro-service, dealing with reading the ARTEMIS configuration from a file (YAML); the file
contains information about: prefixes, ASNs, monitors and ARTEMIS rules (e.g., "ASX advertises prefix P to ASY").
* Detection micro-service, providing real-time detection of BGP prefix hijacking attacks/events of the following types:
  * exact-prefix type-0/1
  * sub-prefix (of any type)
  * squatting attacks
* Mitigation micro-service, providing manual or manually controlled mitigation of BGP prefix hijacking attacks.
* Observer micro-service, dealing with the monitoring of the changes in the ARTEMIS configuration file, triggering the reloading of the affected micro-services.
* Scheduler micro-service, providing a clock service for periodical messages consumed by different micro-services.
* Postgres DB access micro-service, providing programmatic R+W access to the main database of ARTEMIS.
* Supervisord for managing the backend services of the system as processes, and listener micro-service to listen for changes in the process status (e.g., running --> stopped).
* Integration of Monitor, Configuration, Detection, Mitigation, Observer, Scheduler and Postgres DB micro-service in ARTEMIS
"backend".
* Integrated HTTPS frontend/web interface used by the network administrator to:
  * register to the system (ADMIN role: R+W access, VIEWER role: R access)
  * provide configuration information (ASNs, prefixes, routing policies, etc.) via a web-based text editor
  * comment on the configuration file that is used as the system input
  * view and compare past configuration files, using their timestamps to disambiguate them
  * control Monitor, Detection and Mitigation micro-services (start/stop)
  * view the status of all micro-services live (on/off/uptime)
  * view in real-time the BGP updates (announcements/withdrawals) related to the (configured) IP prefixes of interest,
with the following capabilities:
    * per-prefix grouping
    * live update/offline mode
    * time window tuning
    * number of visible entries tuning
    * paginated viewing
    * basic information per update (timestamp, prefix, origin AS, AS-path, peer AS, route collector service, type, hijack, status)
    * auxiliary information per route collector that has seen the BGP update(s) (mouse hover)
    * auxiliary information per update (original AS-path, communities, hijack key, matched prefix)
    * ASN, name, private or not, and countries of operation for origin and peer ASes, as well as ASes present on an AS-path (mouse hover)
    * sorting per update timestamp
    * searching updates using the prefix, origin AS, peer AS, service, and/or update type fields
    * downloading the (filtered) bgp updates table in json format
    * displaying the distinct values involved in the prefix, origin AS, peer AS, service and type fields
  * view in real-time the BGP prefix hijacking events related to the (configured) IP prefixes of interest,
with the following capabilities:
    * per-prefix grouping
    * live update/offline mode
    * time window tuning
    * number of visible entries tuning
    * paginated viewing
    * basic information per hijack (time detected, status, prefix, type, hijack AS, number of peers seen, number of ASes infected, seen)
    * auxiliary information per hijack (matched prefix, first matched configuration, hijack key, time started, time last updated, time ended,
time mitigation started, peer ASes that saw announcements/withdrawals, BGP updates related to this hijack)
    * buttons to mark an individual hijack as seen, resolve, mitigate or ignore it
    * comment box to associate a hijack with a certain comment
    * group actions to mark multiple hijacks as seen/not seen, ignored, or resolved
    * ASN, name, private or not, and countries of operation for hijack ASes (mouse hover)
    * sorting per time detected timestamp
    * searching hijacks using the prefix, hijack type, and/or hijack AS fields
    * downloading the (filtered) hijacks table in json format
    * displaying the distinct values involved in the prefix, type and hijack AS fields
  * view the status of a hijack: ongoing, ignored, resolved, under mitigation, withdrawn, outdated
  * automatic characterization of a hijack as withdrawn if all the monitor peers that saw a hijack update saw also a withdrawal
  * automatic characterization of a hijack as outdated if the configuration that triggered the hijack is outdated
  * view DB statistics (total/unhandled BGP updates, total/resolved/ignored/under mitigation/ongoing/ignored/withdrawn/outdated/seen hijacks)
  * view help boxes for every field used in the system (mouse hover)
  * view additional login information
  * change password
  * manage users
  * view visualization of per-prefix AS-level graphs (until the first hop neighbor), according to configuration
* User interface for both mobile and desktop environments
* Support for both IPv4 and IPv6 prefixes
* Support for handling AS-Sets, Confederations, AS sequences, path prepending, loops, etc. appearing during the monitoring + detection processes
* Support for email/syslog/other notifications for new hijacks
* Daily backups of the ARTEMIS DB
* Scalable RabbitMQ message bus (container) for the message passing and queueing for all involved micro-services and containers
* Timescale + Postgres container for persistent storage and efficient data indexing
* Postgrest container for REST API to Postgres DB
* Hasura graphql container for asynchronous access to Postgres DB
* Pg_amqp bridge container for asynchronous communication between Postgres DB and RabbitMQ
* Redis DB for ephemeral storage in the backend
* NGINX server for terminating SSL connections before propagating to the frontend
* Gunicorn for HTTP request load balancing
* Flask for the frontend (used as proxy)
* Support for automated migration of the ARTEMIS DB to new versions
* Cython support for optimized performance
* JWT authentication in graphql
* DB access optimized via indexes
* Composition of multiple containers via docker-compose
* Support for running multiple detector instances
* Optional support for Kubernetes setups (single physical machine)

### Changed
- NA (Not Applicable)

### Fixed
- NA

### Removed
- NA

### Deprecated
- NA

### Security
- NA

# TEMPLATE FOR NEW RELEASES
## [RELEASE_VERSION] (NAME) - YYYY-MM-DD
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
