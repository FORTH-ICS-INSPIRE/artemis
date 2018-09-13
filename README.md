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
on the INSPIRE Group ARTEMIS webpage: http://www.inspire.edu.gr/artemis.

This repository contains the software of ARTEMIS as a tool (essentially a highly
modular, multi-container application).

## Features

The current version of ARTEMIS as a tool includes the following features:

* Real-time monitoring of the inter-domain routing control plane using
feed from BGP route collectors via [RIPE RIS](http://stream-dev.ris.ripe.net/demo),
[BGPStream](https://bgpstream.caida.org/) (RouteViews + RIPE RIS) and
[exaBGP](https://github.com/Exa-Networks/exabgp) (local monitor) interfaces.
* Detection of basic types of BGP prefix hijacking attacks/events,
i.e., exact-prefix type-0/1, sub-prefix of any type, and squatting attacks.
* Manual mitigation of BGP prefix hijacking attacks.
* User interface to configure the tool, have an overview of the
inter-domain control plane state related to the IP prefixes of interest,
and get notified about BGP hijacks against the prefixes of the network
which is running ARTEMIS.
* Support for both IPv4 and IPv6 prefixes.
* Modularity/extensibility by design.
* (TBD)


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
* RAM: 4-8 GB
* HDD: 30 GB
* NETWORK: 2 network interfaces
* OS: Ubuntu Linux 16.04+
* Other: SW package manager, SSH server (optional)

Moreover, one needs to configure the following firewall rules related to the testing server/VM (TBD):

| Service | Direction+ | Action | Reason |
| --- | --- | --- | --- |
| ssh | Internet to Server | Allow| Access server from specific IPs |
| ping (ICMP) |Internet to Server | Allow | Ping server from specific IPs
| http/https | Server to Internet | Allow | Access to external monitors
| https | Internet to Server | Allow | Access web UI from specific IPs |
| TCP port 179 | Internal: server to/from route reflector | Allow | exaBGP local monitor communication with route reflector |
| any | any | Deny | --- |

+: related reverse direction for bilateral session over stateful firewall needs also to pass though

## How to install
First, if not already installed, follow the instructions
[here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce)
to install the latest version of the docker tool for managing containers,
and [here](https://docs.docker.com/compose/install/#install-compose)
to install the docker-compose tool for supporting multi-container Docker applications.

If you would like to run docker without using sudo, please add
the local user to the default docker group:
```
sudo usermod -aG docker $USER
```

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
TBD
```
and adjusting the following parameters/environment variables (TBD):
```
TBD
```

### SSL/TLS Support (optional; TBD)
The ARTEMIS web application supports https to ensure secure access to the application state.

*Note:* The following associated process, based on Flask-accessed certificates/keys,
is to be used only termporarily in testing environments.
In production, a scalable nginx/apache-based reverse proxy will be used
to terminate SSL connections (TBD).

For testing, simply configure the following in the web application configuration file (TBD) as environment variables:
```
WEBAPP_KEY = '<path_to_key_file>'
WEBAPP_CRT = '<path_to_cert_file>'
```

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
TBD (for now working on the bleeding edge of the master branch, version tags to-be-released)

## Authors
* Dimitrios Mavrommatis, FORTH-ICS
* Petros Gigis, FORTH-ICS
* Vasileios Kotronis, FORTH-ICS

## License
TBD (closed source until further notice; considering BSD-3 license but not definitive yet)

## Acknowledgements
This work is supported by the following sources:
* European Research Council (ERC) grant agreement no. 338402 (NetVolution Project)
* RIPE NCC Community Projects Fund
