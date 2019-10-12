[![Build Status](https://semaphoreci.com/api/v1/slowr/artemis/branches/master/shields_badge.svg)](https://semaphoreci.com/slowr/artemis)
[![CodeFactor](https://www.codefactor.io/repository/github/forth-ics-inspire/artemis/badge)](https://www.codefactor.io/repository/github/forth-ics-inspire/artemis)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Coverage Status](https://coveralls.io/repos/github/FORTH-ICS-INSPIRE/artemis/badge.svg?branch=master)](https://coveralls.io/github/FORTH-ICS-INSPIRE/artemis?branch=master)
[![Discord](https://img.shields.io/badge/chat-discord-brightgreen.svg?logo=discord&style=flat)](https://discord.gg/8UerJvh)
[![Mailing list](https://img.shields.io/badge/mail-ARTEMIS-green.svg)](http://lists.ics.forth.gr/mailman/listinfo/artemis)
![Release](https://img.shields.io/github/release/FORTH-ICS-INSPIRE/artemis.svg?style=flat)
[![License](https://img.shields.io/badge/license-BSD--3-blue.svg)](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/LICENSE)

#

<p align="center">
<img src="docs/images/artemis_logo.png" style="margin-bottom: 15px;"/>
</p>

![](overview.gif)

Table of Contents
  * [General](#general)
  * [Features](#features)
  * [Architecture](#architecture)
  * [Getting Started](#getting-started)
  * [Minimum Technical Requirements](#minimum-technical-requirements)
  * [How to Install and Setup](#how-to-install-and-setup)
  * [How to Run and Configure](#how-to-run-and-configure)
  * [Demo](#demo)
  * [Contributing](#contributing)
  * [Development Team and Contact](#development-team-and-contact)
  * [Versioning](#versioning)
  * [Authors and Contributors](#authors-and-contributors)
  * [License](#license)
  * [Acknowledgements and Funding Sources](#acknowledgements-and-funding-sources)
  * [Powered By](#powered-by)

<p align="left">
<img src="docs/images/inst_logos/forth_logo.png" height="92" width="300" style="margin-bottom: 15px;"/>
<img src="docs/images/inst_logos/caida_logo.png" height="143" width="100" hspace="50"/>
</p>

## General

ARTEMIS is a defense approach against BGP prefix hijacking attacks.
It is (a) based on accurate and fast detection operated by the AS itself,
by leveraging the pervasiveness of publicly available BGP monitoring
services and it (b) enables flexible and fast mitigation of hijacking events.
Compared to existing approaches/tools, ARTEMIS combines characteristics
desirable to network operators such as comprehensiveness, accuracy, speed,
privacy, and flexibility. With the ARTEMIS approach, prefix hijacking
can be neutralized within a minute!

**NOTE: Depending on the preferences of the user, ARTEMIS can be used in 3 basic modes depending on the combination of enabled micro-services in the user interface:**
1. Passive monitor (monitoring enabled)
2. Passive detector (monitoring + detection enabled)
3. Active joint detector and user-triggered mitigator (monitoring + detection + mitigation enabled)

*Any of these combinations is valid. To start with, we recommend using mode (2).*
Mode (3) is under development (currently only a mitigation wrapper is offered).

You can read more about the ARTEMIS methodology and research experiments
on the ARTEMIS [webpage](http://www.inspire.edu.gr/artemis).

This repository contains the software of ARTEMIS as a tool.
ARTEMIS can be run on a server/VM as a modular and extensible
multi-container application. It has been tested at a major
greek ISP, a dual-homed edge academic network,
and a major US R&E backbone network.

## Features

For a detailed list of supported features please check the [CHANGELOG](CHANGELOG.md) file
(section: "Added"). The following main features are supported:

* Real-time monitoring of the changes in the BGP routes of the prefixes originated by the AS running ARTEMIS.
* Real-time detection and notifications of BGP prefix hijacking attacks/events of the following types (please refer to the attack taxonomy in our [ARTEMIS ToN paper](https://www.inspire.edu.gr/wp-content/pdfs/artemis_TON2018.pdf)):
  * exact-prefix, type 0/1, any data plane manipulation
  * sub-prefix, any type (0/1/-), any data plane manipulation
  * squatting attacks, type 0 (others are N/A), any data plane manipulation
  * policy violations (route leaks) due to long paths towards no-export prefixes
* Automatic/custom tagging of detected BGP hijack events (ongoing, resolved, ignored, under mitigation, withdrawn, outdated and dormant).
* Manual or manually controlled mitigation of BGP prefix hijacking attacks.
* Comprehensive web-based User Interface (UI).
* Configuration file editable by the operator (directly or via the UI),
containing information about: prefixes, ASNs, monitors and ARTEMIS rules ("ASX originates prefix P and advertises it to ASY").
* Support for both IPv4 and IPv6 prefixes (millions of routed prefixes depending on your resources).
* Support for both mobile and desktop environments (UI): [sample screenshots](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/UI-how-to-and-screenshots).
* Support for docker-compose (local deployment) and Kubernetes (helm charts).
* Support for multiple modes of operation (passive monitor/detector, active mitigator, etc.).
* Modularity/extensibility by design.
* CI/CD.

## System Architecture

![Architecture](docs/images/artemis_system_overview.png)

## Getting Started

ARTEMIS is built as a multi-container Docker application.
The following instructions will get you a containerized
copy of the ARTEMIS tool up and running on your local machine. For instructions on how to set up ARTEMIS
in a Kubernetes environment, please contact the [ARTEMIS team](#development-team-and-contact).

## Minimum Technical Requirements

* CPU: 4 cores (note that needed CPU cores depend on the number of separate processes, e.g., detectors, you spawn)
* RAM: 4+ GB (note that needed memory depends on the number of configured prefixes/rules/asns and load of incoming BGP updates, see [here](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#memory-requirements))
* HDD: 100 GB (less may suffice, depending on the use case for storing BGP updates and hijack alerts)
* NETWORK: 1 public-facing network interface
* OS: Ubuntu Linux 16.04+
* SW PACKAGES: docker-ce and docker-compose should be pre-installed (see instructions later)
and docker should have sudo privileges, if only non-sudo user is allowed
* Other: SSH server

Moreover, one may optionally configure firewall rules related to the server/VM.
We recommend using [ufw](https://www.digitalocean.com/community/tutorials/how-to-set-up-a-firewall-with-ufw-on-ubuntu-16-04)
for this task. Please check the comments in the respective script we provide and
set the corresponding <> fields in the file before running:
```
sudo ./other/ufw_setup.sh
```
**NOTE: For security reasons, we highly recommend protecting your machine with such rules.**

## How to Install and Setup

To download and install the required software packages, please follow steps 1 through 6 described in [this Wiki section](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#install-packages).

To setup the tool (as well as https access to it via the web application), please follow steps 1 through 5 described in [this Wiki section](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#setup-tool).

## How to Run and Configure

1. Start ARTEMIS:

   ```
   docker-compose up -d
   ```
   *Please consult [this Wiki section](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#starting-artemis) if you need to activate additional services.*

5. Visit web UI and configure ARTEMIS:

   ```
   https://<ARTEMIS_HOST>
   ```
   By visiting the system page:
   ```
   https://<ARTEMIS_HOST>/admin/system
   ```
   you can:
   1. edit the basic configuration file of ARTEMIS that servers as the ground truth for detecting BGP hijacks (consult [this Wiki section](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki/Configuration-file))
   2. control the monitoring, detection and mitigation modules.

6. Stop ARTEMIS (optional)

   ```
   docker-compose stop
   ```

**Note: We highly recommend going through the detailed wiki instructions before using ARTEMIS for the first time.**

## Demo

A running demo of ARTEMIS based on the configuration of our home institute (FORTH) can be found [here](http://www.inspire.edu.gr/artemis/demo/).
You can access the demo as a guest (non-admin) user by using the following credentials:
* username: "guest"
* password: "guest@artemis2018"

*Please do not request new accounts on the demo portal. Use the given credentials to browse ARTEMIS as a guest user.*

## Contributing

Please check [this file](CONTRIBUTING.md).

## Development Team and Contact

We follow a custom Agile approach for our development.

If you need to contact us about a bug, an issue or a question you have; you can reach us over at our [Discord Community Server](https://discord.gg/8UerJvh). Otherwise, you can contact the ARTEMIS developers via e-mail using the [ARTEMIS mailing list](http://lists.ics.forth.gr/mailman/listinfo/artemis).

## Versioning

Please check [this file](CHANGELOG.md).

## Authors and Contributors

Please check [this file](AUTHORS.md).

## License

The ARTEMIS software is open-sourced under the BSD-3 license.
Please check the [license file](LICENSE).

Note that all external dependencies are used in a way compatible with BSD-3
(that is, we conform to the compatibility rules of each and every dependency);
the associated software packages and their respective licenses are documented
in detail in [this file](DEPENDENCIES-LICENSES.md), where we provide links
to their homepages and licenses. Please let us know in case any of the information
contained there is out-of-date to update it.

## Acknowledgements and Funding Sources

This work is supported by the following funding sources on the European side (FORTH):
* **European Research Council (ERC) grant agreement no. 790575 ([PHILOS Project](https://cordis.europa.eu/project/rcn/215015/en))**
* **European Research Council (ERC) grant agreement no. 338402 ([NetVolution Project](http://netvolution.eu/))**
* **[RIPE NCC Community Projects Fund](https://www.ripe.net/publications/news/announcements/ripe-community-projects-fund-2017-recipients-announced)**

The following funding sources supported the collaboration with CAIDA UCSD, on the US side:
* **National Science Foundation (NSF) grants OAC-1848641 and CNS-1423659**
* **Department of Homeland Security (DHS) Science and Technology Directorate, Cyber Security Division (DHS S&T/CSD) via contract number HHSP233201600012C**
* **Comcast Innovation Fund**

## Powered By
<p align="center">
<img src="docs/images/powered_by/bgpstream.png" width="100"/>
<img src="docs/images/powered_by/bootstrap.png" width="100"/>
<img src="docs/images/powered_by/exabgp.jpg" width="100"/>
<img src="docs/images/powered_by/flask.png" width="100"/>
<img src="docs/images/powered_by/gunicorn.png" width="100"/>
<img src="docs/images/powered_by/hasura.png" width="100"/>
<img src="docs/images/powered_by/jquery.png" width="100"/>
<img src="docs/images/powered_by/nginx.jpeg" width="100"/>
<img src="docs/images/powered_by/postgresql.png" width="100"/>
<img src="docs/images/powered_by/python.jpeg" width="100"/>
<img src="docs/images/powered_by/rabbitmq.png" width="100"/>
<img src="docs/images/powered_by/redis.png" width="100"/>
<img src="docs/images/powered_by/sqlite.jpeg" width="100"/>
</p>

*DISCLAIMER: We do not own these logo images. All links to the respective project pages
from where the logos were downloaded are contained in [this file](DEPENDENCIES-LICENSES.md),
together with their respective licenses. The sole purpose of this section is to thank the
open-source software projects that enabled ARTEMIS with their functionality and APIs,
by making them as visible as possible.
The list of project logos is not exhaustive. Image copyright is retained by the respective project's copyright owners.*
