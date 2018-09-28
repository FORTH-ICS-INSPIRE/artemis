# ARTEMIS

## General

ARTEMIS is a defense approach versus BGP prefix hijacking attacks
(a) based on accurate and fast detection operated by the AS itself,
leveraging the pervasiveness of publicly available BGP monitoring
services and their recent shift towards real-time streaming,
thus (b) enabling flexible and fast mitigation of hijacking events.
Compared to existing approaches/tools, ARTEMIS combines characteristics
desirable to network operators such as comprehensiveness, accuracy, speed,
privacy, and flexibility. With the ARTEMIS approach, prefix hijacking
can be neutralized within a minute!

You can read more about ARTEMIS (and check e.g., news and related publications)
on the INSPIRE Group ARTEMIS [webpage](http://www.inspire.edu.gr/artemis.)

This repository contains the software of ARTEMIS as a tool.
ARTEMIS can be run on a testing server/VM as a modular
multi-container application.

## Features

The current version of ARTEMIS as a tool includes the following features:

* Real-time monitoring of the changes in the BGP routes of the network's prefixes.
ARTEMIS connects and receives real-time feeds of BGP updates from the streaming
BGP route collectors of [RIPE RIS](http://stream-dev.ris.ripe.net/demo) and
[BGPStream](https://bgpstream.caida.org/) (RouteViews + RIPE RIS).
Optionally, it connects to and receives BGP information from local routers through
[exaBGP](https://github.com/Exa-Networks/exabgp).
* Real-time detection of BGP prefix hijacking attacks/events of the following types:
exact-prefix type-0/1, sub-prefix of any type, and squatting attacks.
* Manual mitigation of BGP prefix hijacking attacks. Upon the detection of a
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
* Web interface used by the network administrator to:
(i) provide configuration
information (ASNs, prefixes, routing policies, etc.) via a web form or text editor,
(ii) control ARTEMIS modules (start/stop/status),
(iii) monitor in real-time the BGP state related to the IP prefixes of interest,
(iv) view details of BGP hijacks of monitored prefixes,
(v) monitor in real-time the status of ongoing, unresolved BGP hijacks,
(vi) press button to trigger a custom mitigation process, mark as manually mitigated ("resolve")
or ignore the event as a false positive,
(vii) register and manage users (ADMIN|VIEWER).
* Configuration file editable by the operator (directly or via the web interface),
containing information about: prefixes, ASNs, monitors and ARTEMIS rules ("ASX advertises prefix P to ASY").
* CLI to start/stop ARTEMIS modules and query their status (running state, uptime).
* Support for both IPv4 and IPv6 prefixes.

## Architecture (current, tentative)

![Architecture](docs/images/modular_artemis_arch.png)

More details on the design of ARTEMIS and how its different modules
interact with each other will be added to this README soon.

## Getting Started

ARTEMIS is built as a multi-container Docker application.
The following instructions will get you a containerized
copy of the ARTEMIS tool up and running on your local machine
for testing purposes.

## Min. technical requirements of testing server/VM (TBD)

* CPU: 4 cores
* RAM: 4 GB
* HDD: 100 GB
* NETWORK: 1 public-facing network interface
* OS: Ubuntu Linux 16.04+
* SW PACKAGES: docker-ce and docker-compose should be pre-installed
and docker should have sudo privileges, if only non-sudo user is allowed
* Other: SSH server

Moreover, one needs to configure firewall rules related to the testing server/VM. We recommend using [ufw](https://www.digitalocean.com/community/tutorials/how-to-set-up-a-firewall-with-ufw-on-ubuntu-16-04) for this task. Please check the comments in the respective script we provide and set the corresponding <> fields in the file before running:
```
sudo ./ufw_setup.sh
```

## How to install
First, if not already installed, follow the instructions
[here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce)
to install the latest version of the docker tool for managing containers,
and [here](https://docs.docker.com/compose/install/#install-compose)
to install the docker-compose tool for supporting multi-container Docker applications.

If you would like to run docker without using sudo, please create
a docker group, if not existing:
```
sudo groupadd docker
```
and then add the user to the docker group:
```
sudo usermod -aG docker $USER
```
For more instructions and potential debugging on this please consult this
[webpage](https://docs.docker.com/install/linux/linux-postinstall/#manage-docker-as-a-non-root-user).

Then you can build ARTEMIS by running:
```
docker-compose build
```
after you have entered the root folder of the cloned ARTEMIS repo.

## How to run

### Configuring the web application
Before starting ARTEMIS, you should configure the web application
(used to configure/control ARTEMIS and view its state),
by editing the following file (TBD):
```
docker-compose.yml
```
and adjusting the following parameters/environment variables (TBD):
```
TBD
```

You should also edit the following file (TBD):
```
frontend/webapp/configs/webapp.cfg
```
and adjust the following parameters (TBD):
```
TBD
```

### SSL/TLS Support (optional; TBD)
The ARTEMIS web application supports https to ensure secure access to the application.

*Note:* The following associated process, based on Flask-accessed certificates/keys,
is to be used only termporarily in testing environments.
In production, a scalable nginx/apache-based reverse proxy will be used
to terminate SSL connections (TBD).
For testing, simply configure the following in the web application configuration file:
```
WEBAPP_KEY = '<path_to_key_file>'
WEBAPP_CRT = '<path_to_cert_file>'
```

### Configuring logging (syslog)
You should edit the following file:
```
docker-compose.yml
```
and adjust the following environment variables:
```
SYSLOG_HOST=<IP>:<PORT>
```
for the artemis and artemis_webapp services.

### Starting ARTEMIS
You can start ARTEMIS as a multi-container application
by running:
```
docker-compose up
```

### Using the web application
Visually, you can now configure, control and view ARTEMIS on https://<WEBAPP_HOST>:<WEBAPP_PORT> (TBD). 
More instructions on how to use the ARTEMIS web application will be available soon.

*Note*: Please use only the web application forms to configure ARTEMIS.

### Registering users (ADMIN/VIEWER)
```
TBD
```

### Configuring ARTEMIS through the web application
```
TBD
```

### Controlling ARTEMIS through the web application
```
TBD
```

### Viewing BGP updates and hijacks
```
TBD
```

### Other (TBD)
```
TBD
```

### CLI controls

You can also control ARTEMIS (if required) via a CLI, by executing the following command(s):
```
docker exec -it artemis python3 scripts/module_control.py -m <module> -a <action>
```
Note that module = all|configuration|scheduler|postgresql_db|monitor|detection|mitigation,
and action=start|stop|status.

Also note that the web application operates in its own separate container; to stop and e.g., restart it, please run the following commands:
```
TBD
```

### Receiving BGP feed from local route reflector via exaBGP
For instructions on how to set up an exaBGP-based local monitor,
getting BGP updates' feed from your local router or route reflector,
please check [here](https://github.com/slowr/ExaBGP-Monitor)

In ARTEMIS, you should configure the monitor using the web application form,
by setting its IP address and port (default=TBD). An example is the following:
```
TBD
```

### Exiting ARTEMIS

Note that to gracefully terminate ARTEMIS and all its services you can use the following commands:

```
Ctrl+C # on the terminal running ARTEMIS
docker-compose down # afterwards, same terminal
```

## Known Issues

1. iptables: No chain/target/match by that name
```
docker: Error response from daemon: driver failed programming
external connectivity on endpoint artemistest (4980f6b7fe169a16e8ebe5f5e01a31700409d17258da0ee19ea060060d3f3db9):
(iptables failed: iptables --wait -t filter -A DOCKER ! -i docker0 -o docker0 -p tcp -d 172.17.0.2
--dport 5000 -j ACCEPT: iptables: No chain/target/match by that name.
(exit status 1)).
```

To fix, clear all chains and then restart Docker Service:
```
iptables -t filter -F
iptables -t filter -X
systemctl restart docker
```

## Contributing

### Implementing additional Monitors (taps)
```
TBD
```
For example take a look at the `backend/taps/exabgp_client.py`
which implements the exaBGP monitor publisher or
the `backend/taps/ripe_ris.js` which implements the
RIPE RIS monitor publisher. Please edit only the code
in the taps folder.

### Adding custom (containerized) modules
```
TBD
```

## Development
We follow a custom Agile approach for our development.

## Versioning
TBD (version tags to-be-released)

## Authors
* Dimitrios Mavrommatis, FORTH-ICS
* Petros Gigis, FORTH-ICS
* Vasileios Kotronis, FORTH-ICS

## License
We are finalizing the process of open-sourcing the ARTEMIS software under the BSD-3 license. A provisional [license](LICENSE) has been added to the code.
During the testing phase and until ARTEMIS is fully open-sourced, the tester is allowed to have access to the code and use it,
but is not allowed to disclose the code to third parties.

## Acknowledgements
This work is supported by the following sources:
* European Research Council (ERC) grant agreement no. 338402 (NetVolution Project)
* RIPE NCC Community Projects Fund
