# ARTEMIS

ARTEMIS is a defense approach versus BGP prefix hijacking attacks (a) based on accurate and fast detection operated by the AS itself, leveraging the pervasiveness of publicly available BGP monitoring services and their recent shift towards real-time streaming, thus (b) enabling flexible and fast mitigation of hijacking events. Compared to existing approaches/tools, ARTEMIS combines characteristics desirable to network operators such as comprehensiveness, accuracy, speed, privacy, and flexibility. With the ARTEMIS approach, prefix hijacking can be neutralized within a minute!

You can read more on INSPIRE Group ARTEMIS webpage: http://www.inspire.edu.gr/artemis.

The current version of ARTEMIS as a tool includes the following features:

* Real-time monitoring of the inter-domain routing control plane using feed from BGP route collectors via [RIPE RIS](http://stream-dev.ris.ripe.net/demo), [BGPStream](https://bgpstream.caida.org/) (RouteViews + RIPE RIS) and [exaBGP](https://github.com/Exa-Networks/exabgp) (local monitor) interfaces.
* Detection of basic types of BGP prefix hijacking attacks/events, i.e., exact-prefix type-0/1, sub-prefix of any type, and squatting attacks.
* Manual mitigation of BGP prefix hijacking attacks.
* User interface to configure the tool, have an overview of the inter-domain control plane state related to the IP prefixes of interest, and get notified about BGP hijacks against the prefixes of the network which is running ARTEMIS.
* Support for both IPv4 and IPv6 prefixes.
* Modularity/extensibility by design.

*Note*: All current development is taking place on the kombu branch, which contains a significant refactoring of the tool's code. The master branch will be up-to-date by September the 13th, 2018.

## Getting Started

ARTEMIS is built as a multi-container Docker application. The following instructions will get you a containerized copy of the ARTEMIS tool up and running on your local machine for testing purposes. For a detailed view of the ARTEMIS system architecture please check [here](https://docs.google.com/presentation/d/104ENSvv7c-4jZ14BDAAqvK8bSUIWHV7g0TiNqT71J4s/edit?usp=sharing).

## How to run

First, if not already installed, follow the instructions [here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce) to install the latest version of docker, and [here](https://docs.docker.com/compose/install/#install-compose) to install the docker-compose tool for supporting multi-container Docker applications.

If you would like to run docker without using sudo, please add the local user to the default docker group:

```
sudo usermod -aG docker $USER
```

NOTE: THE FOLLOWING INSTRUCTIONS ARE DEPRECATED: TO BE REPLACED WITH DOCKER-COMPOSE COMMANDS

If you do not have access to the inspiregroup/artemis-tool image you can build your own by running:

```
docker build -t inspiregroup/artemis-tool .
```
after you have entered the root folder of the cloned artermis repo.

Otherwise, you can simply pull the latest build from dockerhub:
```
docker login
docker pull inspiregroup/artemis-tool
```

Then, create a directory that includes the `config.yaml`, `webapp.cfg` and `logging.json` configuration files, after configuring them accordingly (see samples).

The application can be run in three different modes: `prod`, `dev` and `testing`. By default, the `dev` mode is selected, and you can modify that by having an environment variable set like this:

```
export FLASK_CONFIGURATION=prod
```

Then, you need to run the container with the following command:

```
docker run --rm -ti -p 5000:5000 -e FLASK_CONFIGURATION=prod --expose 5000 --name artemis -v absolute/path/to/config/directory:/root/configs inspiregroup/artemis-tool
```

Fields:
```
-p: Sets a proxy that maps host's PORT to container's PORT (in this example host's 5000 to container's 5000)
--expose: Exposes from the container the PORT ARTEMIS is running on (specified in `webapp.cfg`)
-ti: Makes container interactive
-v src:dst: Creates a volume in dst path on the container that is a copy of src directory on host
-e name:value: Creates an environment variable on the container to set up the mode of the application.
```

You can now control and view ARTEMIS on <WEBAPP_HOST>:<WEBAPP_PORT>.

Note that to gracefully terminate ARTEMIS and all its sub-threads you can use the following command:

```
docker stop inspiregroup/artemis-tool
```
or
```
kill <ARTEMIS_PID>
```
using the SIGTERM signal.

Note: to run the mininet demo (optional) please follow the instructions under mininet-demo/README.md


## SSL/TLS Support

The following process, based on Flask-accessed certificates/keys, is to be used only in testing environments.

In production, a scalable nginx/apache-based reverse proxy will be used to terminate SSL connections (TBD).

For testing, simply configure the following in configs/webapp.cfg:
```
WEBAPP_KEY = '<path_to_key_file>'
WEBAPP_CRT = '<path_to_cert_file>'
```

## Known Issues

1. iptables: No chain/target/match by that name

```
docker: Error response from daemon: driver failed programming external connectivity on endpoint artemistest (4980f6b7fe169a16e8ebe5f5e01a31700409d17258da0ee19ea060060d3f3db9):  (iptables failed: iptables --wait -t filter -A DOCKER ! -i docker0 -o docker0 -p tcp -d 172.17.0.2 --dport 5000 -j ACCEPT: iptables: No chain/target/match by that name.
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


NOTE: THE FOLLOWING INSTRUCTIONS ARE DEPRECATED: TO BE REPLACED WITH RABBITMQ AND TAPS INSTRUCTIONS

In order to add new monitors you need to send the BGP Update messages to the GRPC Server which runs on port 50051. The .proto file is provided and you only need to compile and use the `queryMformat` function with the provided format:

```
message Community {
  int32 asn = 1;
  int32 value = 2;
}

message MformatMessage {
  string service = 1;
  string type = 2;
  string prefix = 3;
  repeated int32 as_path = 4;
  repeated Community communities = 5;
  double timestamp = 6;
}
```

For example take a look at the `taps/exabgp_client.py` which implements the python GRPC Client or `taps/ripe_ris.js` which implements the javascript GRPC Client. Please edit only the code in the taps folder.
Note that if you need to create a new M-format you need to follow the instructions on the [GRPC website](https://grpc.io/).

## Versioning
TBD (for now working on the bleeding edge of the master branch, version tags to-be-released)

## Authors
* Dimitrios Mavrommatis, FORTH-ICS
* Petros Gigis, FORTH-ICS
* Vasileios Kotronis, FORTH-ICS
* Pavlos Sermpezis, FORTH-ICS

## License
TBD (closed source until further notice)

## Acknowledgments
This work is supported by the following sources:
* European Research Council (ERC) grant agreement no. 338402 (NetVolution Project)
* RIPE NCC Community Projects Fund
* National Science Foundation (NSF) grant CNS-1423659
* Department of Homeland Security (DHS) Science and Technology Directorate, Cyber Security Division (DHS S&T/CSD) via contract number HHSP233201600012C
