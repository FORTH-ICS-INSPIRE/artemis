# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [UNRELEASED/master] (latest) - YYYY-MM-DD
### Added
- "json" encoding accepted for messages coming from frontend (ignore/resolve/seen/delete/(un-)mitigate)

### Changed
- changes in "dataplane_msms" table and "view_dataplane_msms" view, in order to support the new design of the "dataplane_view" module.
- upgraded artemis-utils to 1.0.10 to include the slacker-log-handler==1.7.1 dep
- migrating from travis to GH actions (under work, not complete)

### Fixed
- autoconfiguration subprefix bug in prefixtree plus new autoconf tests
- vagrant docker-compose.yaml file fix (sync with master)

### Removed
- TBD (removed a feature)

### Deprecated
- TBD (soon-to-be removed feature)

### Security
- TBD (addressing vulnerability)

## [2.0.0] (Boreas) - 2021-01-26
### Added
- Action and necessary logic to un-mitigate a hijack
- Ability to reload targeted services based on what conf section changed
- GET config endpoints to backend and monitor services
- Makefile for local commands (dev/ci)
- Added healthchecks to docker-compose (docker-compose version bumped to 3.4)
- Service reconfiguring flag and status
- Redis no-data-received key expiry logic (default: 60 seconds)
- Hijack detail JSON export

### Changed
- Decoupled microservice architecture for backend and frontend
- Possible states constraint on DB hijacks table to allow orthogonal mitigation tagging
- Orthogonal mitigation/unmitigation tagging
- Heavily refactored docs
- Replaced bulk timer thread with separate process
- Replaced autoignore checker thread with separate process
- Replaced exabgp autoconf thread with separate process
- Display info on new microservices, grouping backend/monitor
- Upgraded requests to 2.25.1
- Upgraded to new bgpstream containers (using also ris and routeviews live sources)
- Full refactoring and upgrade of artemis-utils, refactored all imports (1.0.7)
- Upgraded Flask-JWT-Extended to 3.25.0 to address JWT issue with new browsers
- Upgraded artemis-utils to 1.0.8

### Fixed
- Discard messages with timestamps in future datetime (updated to artemis-utils==1.0.5)
- Check for very old timestamps in DB update handling
- Replaced sets that are not supported by shared manager with lists
- Removed unneeded read locks
- Non-gracefull SIGKILL for taps in case graceful stop delays a lot
- Redis configuration file input

### Deprecated
- 'caida' project in bgpstreamlive
- supervisor support and configuration

## [1.6.0] (Achilles) - 2020-11-02
### Added
- Redirection to login page when session is expired (#404)
- Support RADIUS integration for user authentication (#409)
- Support for GRAPHQL_URI to be set via environment variables, or to take a lazy approach and set HASURA_HOST and HASURA_PORT env variables
- Flag to override BGPStream timestamp (#415)
- Hijack alert auto-ignore mechanism for alerts of limited impact/visibility (#373)
- Env variable to invoke intended process states recovery mechanism
- Reinstated RPKI tests for PRs
- Implicit withdrawals are now generated also on correct (direct) subprefix routing
- Support for fork PRs in travis CI/CD builds and tests
- New dataplane-related table and view (pings and traceroutes)
- PoC mitigation mechanism and setup (deaggregation)
- PoC auto-configuration mechanism and setup
- Coverage for unit tests
- AS Path pre-pending sequence matching support in configuration
- Docs pages

### Changed
- Refactor: Changed exchange / queue names
- Heavily refactored and improved exaBGP-based auto-configuration for speed/scale

### Fixed
- Deleting user also deletes the role mapping (#412)
- Backend Makefile to use currently installed python version
- Frontend Makefile to use specific closure compiler version
- Minor opt fix in Redis RTT calls in DB
- Observer fix (RMQ connection establishment) to deal with threading issues

### Removed
- Autoconf support in historical BGPStream (due to deprecation)

### Deprecated
- Wiki pages

## [1.5.0] (Aeolus) - 2020-05-24
### Added
- Additional ports (8080, 8443) to nginx configuration for rootless docker support
- Application names for all postgres connections
- Database migration check between latest release and current version
- Mechanism to show which modules are (re)loading upon configuration change
- GUNICORN_WORKERS and RABBITMQ_IO_THREAD_POOL_SIZE variables smaller deployments
- ZAP Active and Passive scanning
- Select Page button on hijacks page to select all hijacks on current page

### Changed
- Upgraded nginx to latest release (v1.17)
- Upgrade rabbitmq to latest release (v3.8.3)
- Upgrade postgrest to latest release version (v7.0.0)
- Upgraded hasura-engine to v1.1.0
- Updated version of BGPStream on custom image (mavromat/bgpstream-redis:v1.3-bgpstream)

### Fixed
- LIMIT query planner bug (http://datamangling.com/2014/01/17/limit-1-and-performance-in-a-postgres-query/)
- Added stderr output of supervisor processes on docker-compose logs (Please update your custom supervisor confs if using local_configs)
- Issue with multiple rules for same prefix(es) in detection
- Update RIPE Stat API call for ASN to country mapping
- Minor issue with deprecated version of routinator (upgraded to 0.6.4)
- Observer ujson encoding bug

### Security
- Secured "proxy_api" endpoint from unauthorized access. Thanks to @marcgweg for finding this issue

## [1.4.0] (Ajax) - 2019-12-02
### Added
- Grafana provisioning, env vars and 4 dashboards
  - Artemis::BGP Hijacks per prefix
  - Artemis::BGP Updates per prefix
  - Artemis::BGP Updates per service
  - Artemis::Offending ASes
- Get prefix, origin and neighbor info (communities) from exaBGP or hist 'A'/'W' updates
- autoconf flag in configuration for exaBGP and hist monitors
- autoconf tester
- ENV variable WITHDRAWN_HIJACK_THRESHOLD to consider hijacks withdrawn based on a threshold
- TravisCI and CodeCov support
- Database restart recovery
- CAIDA project support (besides RV, RIS) for bgpstreamlive
- bgpstreamkafka tap
- RPKI status in hijack alerts
- RPKI validator env vars
- optional routinator RPKI validator microservice
- make_release script to automate release pushes

### Changed
- Automatic config file formatting upon config modification
- DB_AUTOCLEAN and dormant hijack thresholds set to 1 day (24h) by default
- Change of conf_lib.py in order to support a list of dicts per prefix
- Always restart containers for smooth server rebooting
- Updated version of BGPStream on custom image (mavromat/bgpstream-redis:v1.2-bgpstream)

### Fixed
- Issue on handle_hijack_update() DB function with multiple selects
- Small fixes in conf_lib
- Blocking deletion of redis hijack keys to avoid race conditions
- Optimization on hijack deletion by storing the keys on redis
- Fix with withdrawal storage also on redis (besides announcements)
- Optimization on RPKI validation to happen periodically instead of per hijack update
- no_ack issue in ARTEMIS microservices (replaced with proper acks)
- non-existent consumer for pg-amq when detection was off (fixed with dynamic trigger (de-)activation)
- ARTEMIS monitor + detection performance issue

### Removed
- Rekeying functionality for hijack updates with deprecated hijack key

### Deprecated
- SemaphoreCI and coveralls
- BetaBMP client (kept support in conf file)
- betabmp conf keyword support
- psycopgs2-binary (2.7.7) with psycopg2 (2.8.4)

## [1.3.1] (Ares) - 2019-10-04
### Added
- IPv6 tests (backend testing)
- PR labeler (GitHub actions)
- Env variable and formatter for selecting hijack log fields
- Env variable for ARTEMIS web host for backend logging
- Logging also withdrawn and outdated hijacks in mail and hijack loggers
- Extra end_tag and hijack_url in hijacks for logging
- Reinstating intended modules on ARTEMIS startup
- Support of multiple artemis instances on a single namespace (k8s)
- Added benchmarker and PR commenter
- TestCafe frontend testing framework

### Changed
- py-radix, substituted with pytricia tree
- dep-licenses updated (with currently used modules)
- Fixed bug with outdated hijacks that remain hijacks
- Fixed bug with BGP updates related to more than one hijacks
- Added outdated_parent logging field to inform logging systems

### Fixed
- Support for millions of prefixes in configuration file
- Ensure ARTEMIS config file is not clobbered on pod restart

### Removed
- ipaddress requirement from frontend (not needed)

### Backwards Incompatible Changes
- :rotating_light: Changed frontend logger from webapp_logger to artemis_logger in logging.yaml and config.py under frontend/webapp/configs.
For old versions you need to replace the name from webapp_logger to artemis_logger in these two files under your local_configs/frontend folder.
- :rotating_light: Changed helm chart labels to support multiple releases per namespace and this breaks helm upgrades.
To migrate to the new version you need to deploy a new installation and migrate the Persistent Volumes Claims (PVC) to the new release by attaching them on the current Persistent Volumes.

## [1.3.0] (Arktos) - 2019-09-12
### Added
- Slack logging package and example
- ARTEMIS logo
- Monitor peers count in stats table (overview)
- Implicit withdrawals generated for benign BGP updates correcting hijacked peer-prefix combinations
- Support for configured ASN ranges
- Community-based annotation support for annotating hijacks
- Local pre-commit hook to check versioning
- Bgpstream historical BGP record collector (per prefix)
- Support for RIPE whois service-resolved AS-SETs in configuration
- Ingress resource for helm-chart (by default supports NGINX Ingress Controller)
- Redis ping/pong check on connection initialization
- In hijack page count the number of peers seen announcement and withdrawal

### Changed
- Refactoring frontend (views, templates and static files are organized inside the folder render)
- Update hasura (1.0.0alpha42 -> 1.0.0alpha45)
- Replaced $.ajax with fetch
- Hijack logger output is now a JSON string
- Decoupled monitor module to another container
- Optional deployment of NGINX container or NGINX Ingress on Kubernetes

### Fixed
- Bug with rule learning (hijack to rule dict) when empty neighbor
- Minor fix in custom mitigation trigger
- Updated configurations for k8s deployment
- Fixed flake8 warnings
- Wrong data.sql for testing
- Bug with single-quoted communities being interpreted as sexagesimal upon automated conf reload
- Monitoring of monitors and restarting them if not seen any BGP updates within user-defined interval
- Avoid detectors being stuck on blpop if token erased
- Fix for historical replay of withdrawals plus bgpstreamhist rate-limit
- Minor: creating implicit withdrawals 1 second after the related benign announcement
- Minor: in handling BGP withdrawals, consider announcements that are strictly newer than the withdrawals
- Various helm (k8s) chart fixes and improvements (see #221)

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

[1.5.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.4.0...1.5.0
[1.4.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.3.1...1.4.0
[1.3.1]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.3.0...1.3.1
[1.3.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.2.0...1.3.0
[1.2.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.1.1...1.2.0
[1.1.1]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.1.0...1.1.1
[1.1.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/compare/1.0.0...1.1.0
[1.0.0]: https://github.com/FORTH-ICS-INSPIRE/artemis/releases/tag/1.0.0
