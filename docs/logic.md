# The basic logic of ARTEMIS

ARTEMIS receives BGP update feeds from public or private monitors in real-time (streaming feed),
cross-checks their information against a local configuration file and makes a reliable inference about
a potential hijack event within seconds, enabling immediate mitigation.

The basic philosophy behind the extensible ARTEMIS software architecture is the use of a message bus (MBUS),
used for routing data messages between different microservices,
which interface with the MBUS between message producers and consumers. Each microservice also provides
a REST API for health-checks, control and configuration.

The following microservices compose ARTEMIS:

* Backend
  * `Autoignore`: automatically ignores hijack alerts of low impact and/or visibility based on user configuration.
  * `Autostarter`: automatically checks the health of the backend-custom and monitor-custom microservices and activates them via their REST interface in case they are down.
  * `Configuration`: configures the rest of the microservices using the configuration file.
  * `Database`: database access and management (stores BGP updates, hijacks and other persistent information in  Postgres).
  * `Detection`: detects BGP hijacks in real-time.
  * `Fileobserver`: detects content changes in the configuration file and notifies configuration.
  * `Mitigation`: triggers custom mitigation mechanisms when the user instructs it.
  * `Notifier`: sends BGP hijack alerts to different logging endpoints, according to user configuration.
  * `Prefixtree`: holds the configuration prefix tree (prefixes bundled with ARTEMIS rules) in-memory for quick lookups.
* Monitor (taps):
  * `riperistap`: collects real-time BGP update information from [RIPE RIS live](https://ris-live.ripe.net/).
  * `bgpstreamlivetap`: collects real-time BGP update information from [RIPE RIS RIB collections](https://bgpstream.caida.org/data#!ris), [RouteViews RIB collections](https://bgpstream.caida.org/data#!routeviews) and [Public CAIDA BMP feeds](https://bgpstream.caida.org/v2-beta#bmp).
  * `bgpstreamkafkatap`: collects real-time BGP update information via `Kafka` from public and [private BMP feeds](https://bgpstream.caida.org/v2-beta#bmp-private).
  * `bgpstreamhisttap`: replays historical BGP updates as described [here](https://bgpartemis.readthedocs.io/en/latest/history/).
  * `exabgptap`: collects real-time BGP update information from local BGP feeds via [exaBGP](https://github.com/Exa-Networks/exabgp).
* Frontend: the frontend/UI of ARTEMIS. It communicates with the backend via GraphQL and REST. Separate mono-repo [here](https://github.com/FORTH-ICS-INSPIRE/artemis-web).
* Other:
  * `redis`: in-memory key-value store.
  * `nginx`: frontend ingress.
  * `rabbitmq`: message bus implementation (using exchanges/queues/producers/consumers).
  * `postgres`: Postgres DB implementation for persistent storage.
  * `postgrest`: REST API to Postgres DB.
  * `pg-amqp-bridge`: Postgres to RabbitMQ bridge.
  * `graphql`: GraphQL API to Postgres DB.
* Auxiliary (optional):
  * `exabgp`: ExaBGP monitor that propagates BGP updates to `exabgptap`.
  * `grafana`: Grafana visualizations of DB contents, etc.

The operator (i.e., the "user") interfaces with the system by filling in a configuration file
and by interacting with the web application (UI) to control the various microservices and
see useful information related to monitoring entries and detected hijacks (including their
current status).

Configuration is imported in all microservices since it is used for monitor
filtering, detection tuning, mitigation configuration and other functions. The feed from
the monitoring microservice (which can stem from multiple BGP monitoring sources around the world,
including local monitors) is validated and transmitted to the detection and db access microservices.
The detection microservice reasons about whether what it sees is a hijack or not; if it is, it
generates a hijack entry which is in turn stored in the DB, together with the corresponding
monitoring entries. Finally, using the web application, the operator can instruct the mitigation
microservice to (un-)mitigate a hijack or mark it as resolved/ignored.

All information (configuration, updates, hijacks and microservice state) is persistently
stored in the DB, which is accessed by the web application.

For brevity we do not elaborate more on further auxiliary microservices.
In case you are interested in more details please check the source code under backend/core or contact the ARTEMIS team.
