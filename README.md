[![Build Status](https://semaphoreci.com/api/v1/slowr/artemis/branches/master/shields_badge.svg)](https://semaphoreci.com/slowr/artemis)
[![CodeFactor](https://www.codefactor.io/repository/github/forth-ics-inspire/artemis/badge)](https://www.codefactor.io/repository/github/forth-ics-inspire/artemis)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Coverage Status](https://coveralls.io/repos/github/FORTH-ICS-INSPIRE/artemis/badge.svg?branch=master)](https://coveralls.io/github/FORTH-ICS-INSPIRE/artemis?branch=master)
[![Discord](https://img.shields.io/badge/chat-discord-brightgreen.svg?logo=discord&style=flat)](https://discord.gg/8UerJvh)
![Release](https://img.shields.io/github/release/FORTH-ICS-INSPIRE/artemis.svg?style=flat)
[![License](https://img.shields.io/badge/license-BSD--3-blue.svg)](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/LICENSE)

# ARTEMIS

<p align="left">
<img src="docs/images/inst_logos/forth_logo.png" height="92" width="300" style="margin-bottom: 15px;"/>
<img src="docs/images/inst_logos/caida_logo.png" height="143" width="100" hspace="50"/>
</p>

Table of Contents
  * [General](#general)
  * [Features](#features)
  * [Architecture](#architecture)
  * [Getting Started](#getting-started)
  * [Minimum Technical Requirements](#minimum-technical-requirements)
  * [How to Install](#how-to-install)
  * [How to Configure and Run](#how-to-configure-and-run)
  * [Demo](#demo)
  * [Contributing](#contributing)
  * [Development Team and Contact](#development-team-and-contact)
  * [Versioning](#versioning)
  * [Authors and Contributors](#authors-and-contributors)
  * [License](#license)
  * [Acknowledgements and Funding Sources](#acknowledgements-and-funding-sources)
  * [Powered By](#powered-by)

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
* Automatic/custom tagging of detected BGP hijack events (ongoing, resolved, ignored, under mitigation, withdrawn and outdated).
* Manual or manually controlled mitigation of BGP prefix hijacking attacks.
* Comprehensive web-based User Interface (UI).
* Configuration file editable by the operator (directly or via the UI),
containing information about: prefixes, ASNs, monitors and ARTEMIS rules ("ASX originates prefix P and advertises it to ASY").
* Support for both IPv4 and IPv6 prefixes.
* Support for both mobile and desktop environments (UI).
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

* CPU: 4 cores
* RAM: 4 GB
* HDD: 100 GB (less may suffice, depending on the use case)
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

## How to Install

1. Make sure that your Ubuntu package sources are up-to-date:

   ```
   sudo apt-get update
   ```

2. If not already installed, follow the instructions [here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce) to install the latest version of the docker tool for managing containers, and [here](https://docs.docker.com/compose/install/#install-compose) to install the docker-compose tool for supporting multi-container Docker applications.

   In production, we have used the following versions successfully:
   ```
   $ docker -v
   Docker version 18.09.0, build 4d60db4
   $ docker-compose -v
   docker-compose version 1.20.0, build ca8d3c6
   ```

3. If you would like to run docker without using sudo, please create a docker group, if not existing:

   ```
   sudo groupadd docker
   ```
   and then add the user to the docker group:
   ```
   sudo usermod -aG docker $USER
   ```
   For more instructions and potential debugging on this please consult this [webpage](https://docs.docker.com/install/linux/linux-postinstall/#manage-docker-as-a-non-root-user).

4. Install ntp for time synchronization:

   ```
   sudo apt-get install ntp
   ```

5. Install git for downloading ARTEMIS:
   ```
   sudo apt-get install git
   ```
   and then download ARTEMIS from github (if not already downloaded).

6. The docker-compose utility is configured to pull the latest **stable** released images that are built remotely on [docker cloud](https://cloud.docker.com/). No further installation/building actions are required on your side at this point.

## How to Configure and Run

Please check our [wiki](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki).

The basic actions that you will need to do, stated here for brevity, are the following:

1. Edit environment variables in .env file (especially the security-related variables)

2. Decouple your configs from the default ones (that are under version control), by doing the following in your local artemis directory:
   ```
   mkdir -p local_configs && \
   mkdir -p local_configs/backend && \
   mkdir -p local_configs/frontend && \
   cp -rn backend/configs/* local_configs/backend && \
   cp -rn backend/supervisor.d local_configs/backend && \
   cp -rn frontend/webapp/configs/* local_configs/frontend
   ```
   and then change the following source mappings in docker-compose.yaml:
   * [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L29) (see also comments in docker-compose.yaml file)  to:
   ```
   - ./local_configs/backend/:/etc/artemis/
   ```
   * [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L33) (see also comments in docker-compose.yaml file) to:
   ```
   - ./local_configs/backend/supervisor.d/:/etc/supervisor/conf.d/
   ```
   * [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L68) (see also comments in docker-compose.yaml file) to:
   ```
   - ./local_configs/frontend/:/etc/artemis/
   ```
   * [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L89) (see also comments in docker-compose.yaml file) to:
   ```
   - ./local_configs/frontend/nginx.conf:/etc/nginx/nginx.conf
   ```
   * [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L93) (see also comments in docker-compose.yaml file) to:
   ```
   - ./local_configs/frontend/certs/:/etc/nginx/certs/
   ```
   The local_configs directory is NOT under version control.

3. Configure certificates and NGINX reverse proxy for https termination
   ```
   local_configs/frontend/certs
   local_configs/frontend/nginx.conf
   ```

4. Start ARTEMIS

   ```
   docker-compose up -d
   ```

5. Visit UI and configure ARTEMIS

   ```
   https://<ARTEMIS_HOST>
   ```

6. Activate backups (recommended)

   ```
   docker-compose exec postgres bash
   crond
   exit
   ```

7. Stop ARTEMIS (optional)

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

If you need to contact us about a bug, an issue or a question you have; you can reach us over at our [Discord Community Server](https://discord.gg/8UerJvh). Otherwise, you can contact the ARTEMIS developers via e-mail as follows:
* Dimitrios Mavrommatis (backend): mavromat_at_ics_dot_forth_dot_gr
* Petros Gigis (frontend): gkigkis_at_ics_dot_forth_dot_gr
* Vasileios Kotronis (coordinator): vkotronis_at_ics_dot_forth_dot_gr

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
to their homepages and licenses.

## Acknowledgements and Funding Sources
This work is supported by the following funding sources on the European side (FORTH):
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
