# Welcome to Artemis

<img src="images/artemis_logo.png" style="margin-bottom: 15px;"/>

## General

ARTEMIS is an open-source tool, that implements a defense approach against BGP prefix hijacking attacks.
It is (a) based on accurate and fast detection operated by the AS itself,
by leveraging the pervasiveness of publicly available BGP monitoring
services, and it (b) enables flexible and fast mitigation of hijacking events.
Compared to existing approaches/tools, ARTEMIS combines characteristics
desirable to network operators such as comprehensiveness, accuracy, speed,
privacy, and flexibility. With the ARTEMIS approach, prefix hijacking
can be neutralized within a minute!

Depending on the preferences of the user, ARTEMIS can be used in 3 basic modes according to the combination of enabled microservices in the user interface:

1. Passive monitor (monitoring enabled)
2. Passive detector (monitoring + detection enabled)
3. Active joint detector and user-triggered mitigation mechanism (monitoring + detection + mitigation enabled)

*Any of these combinations is valid. To start with, we recommend using mode (2).
Mode (3) is under development (currently only a mitigation wrapper is offered).*

You can read more about the ARTEMIS methodology, blog posts, presentations, publications, and research experiments
on the ARTEMIS [webpage](https://bgpartemis.org).

This repository contains the software of ARTEMIS as a tool.
ARTEMIS can be run on a server/VM as a modular and extensible
multi-container (microservice) application. It has been officially tested at
AMS-IX, a major greek ISP, FORTH (a dual-homed edge academic network),
and Internet2 (a major US R&E backbone network).
Several other network operators use it either in production or in a testing environment.

## Features

For a detailed list of supported features please check the [CHANGELOG](changelog.md) file
(sections: "Added"). The following main features are currently supported:

* Real-time monitoring of the changes in the BGP routes of the prefixes originated by the AS(es) running ARTEMIS, via:
  * [RIPE RIS live](https://ris-live.ripe.net/)
  * [RIPE RIS RIB collections](https://bgpstream.caida.org/data#!ris)
  * [RouteViews RIB collections](https://bgpstream.caida.org/data#!routeviews)
  * Local BGP feeds ([exaBGP](https://github.com/Exa-Networks/exabgp))
  * [Private BMP feeds](https://bgpstream.caida.org/v2-beta#bmp-private)
* Real-time detection and notifications of BGP prefix hijacking attacks/events of the following types (please refer to the attack taxonomy in our [ARTEMIS IEEE/ACM ToN paper](https://www.inspire.edu.gr/wp-content/pdfs/artemis_TON2018.pdf)):
  * exact-prefix, type 0/1, any data plane manipulation
  * sub-prefix, any type (0/1/-), any data plane manipulation
  * squatting attacks, type 0 (others are N/A), any data plane manipulation
  * policy violations (route leaks) due to long paths toward no-export prefixes
* Automatic/custom tagging of detected BGP hijack events (ongoing, resolved, ignored, under mitigation, withdrawn, outdated and dormant).
* Manual or manually controlled mitigation of BGP prefix hijacking attacks.
* Comprehensive web-based User Interface (UI).
* Configuration file editable by the operator (directly or via the UI),
containing information about: prefixes, ASNs, monitors and ARTEMIS rules ("ASX originates prefix P and advertises it to ASY").
* Support for both IPv4 and IPv6 prefixes (millions of routed prefixes depending on your resources).
* Support for both mobile and desktop environments (UI): [sample screenshots](https://bgpartemis.readthedocs.io/en/latest/webapp/#ui-overview-with-screenshots).
* Support for `docker-compose` (local single-server deployment) and `Kubernetes` (helm charts).
* Support for multiple modes of operation (passive monitor/detector, active mitigator, etc.).
* Support for historical BGP update replaying.
* Support for automated generation of the configuration file.
* Support for RPKI validation of hijacked prefixes.
* Compatibility with `Grafana` charts.
* Modularity/extensibility by design.
* CI/CD (Travis CI, Codecov).

## System Architecture

Please check [this page](https://bgpartemis.readthedocs.io/en/latest/architecture/).