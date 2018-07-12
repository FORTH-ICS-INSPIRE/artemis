# ARTEMIS

ARTEMIS is a defense approach versus BGP prefix hijacking attacks (a) based on accurate and fast detection operated by the AS itself, leveraging the pervasiveness of publicly available BGP monitoring services and their recent shift towards real-time streaming, thus (b) enabling flexible and fast mitigation of hijacking events. Compared to existing approaches/tools, ARTEMIS combines characteristics desirable to network operators such as comprehensiveness, accuracy, speed, privacy, and flexibility. With the ARTEMIS approach, prefix hijacking can be neutralized within a minute!

You can read more on INSPIRE Group ARTEMIS webpage: http://www.inspire.edu.gr/artemis.

## Getting Started

These instructions will get you a copy of the ARTEMIS tool up and running on your local machine for testing purposes. For a detailed view of the ARTEMIS system architecture please check architecture.txt. We highly recommend using the containerized approach.

## ARTEMIS as Container (Recommended)

### How to run

First, if not already installed, follow the instructions [here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce) to install docker.

If you would like to run docker without using sudo, please add the local user to the default docker group:

```
sudo usermod -aG docker $USER
```

If you do not have access to the mavromat/artemis image you can build your own by running:

```
docker build -t mavromat/artemis .
```
after you have entered the root folder of the cloned artermis repo.

Then, create a directory that includes the `config` and `webapp.cfg` configuration files.

Then, you need to run the container with the following command:

```
docker run -ti -p 5000:5000 --expose 5000 --name artemis -v absolute/path/to/config/directory:/root/configs mavromat/artemis:latest
```

Fields:
```
-p: Sets a proxy that maps host's PORT to container's PORT (in this example host's 5000 to container's 5000)
--expose: Exposes from the container the PORT ARTEMIS is running on (specified in `webapp.cfg`)
-ti: Makes container interactive
-v src:dst: Creates a volume in dst path on the container that is a copy of src directory on host
```

### Known Issues

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

## ARTEMIS from source (Not recommended)

### Dependencies

* [Python 3](https://www.python.org/downloads/)   —  **ARTEMIS** requires Python 3.4.

Install pip3
```
apt-get update && \
apt-get -y install python3-pip
```

Then inside the root folder of the tool run
```
pip3 --no-cache-dir install -r requirements.txt
```

For RIPE RIS monitors you need to install nodejs
```
curl -sL https://deb.nodesource.com/setup_9.x | bash - && \
apt-get install -y nodejs build-essential
```

Then install the needed modules
```
cd taps
npm i npm@latest -g && \
npm install && \
npm audit fix
```

For BGPStream live support (as well as historical data retrieval), you need to follow the
instructions on:
```
https://bgpstream.caida.org/docs/install/bgpstream
https://bgpstream.caida.org/docs/install/pybgpstream
```
in order to install the libbgpstream (core) and the Python library/API pybgpstream. Note to install pybgpstream via:
```
pip3 install pybgpstream
```
For more detailed instructions see the relevant lines of the Dockerfile.

### How to run

To succesfully run ARTEMIS you need to modify the main configuration file

```
vim configs/config
```

Since ARTEMIS includes a Web App and GUI, you also need to modify the webapp configuration file

```
vim configs/webapp.cfg
```

After modifying the configuration files run

```
python3 artemis.py
```

You can now control and view ARTEMIS on <WEBAPP_HOST>:<WEBAPP_PORT>.

Note that to gracefully terminate ARTEMIS and all its sub-threads you can use the following command:

```
kill <ARTEMIS_PID>
```

using the SIGTERM signal.

Note: to run the mininet demo (optional) please follow the instructions under mininet-demo/README.md

### SSL/TLS Support

The following process, based on Flask-accessed certificates/keys, is to be used only in testing environments. 

In production, a scalable nginx/apache-based reverse proxy will be used to terminate SSL connections.

For testing, simply configure the following in configs/webapp.cfg: 
```
WEBAPP_KEY = '<path_to_key_file>'
WEBAPP_CRT = '<path_to_cert_file>'
```

## Contributing

### Implementing additional Monitors (taps)

In order to add new monitors you need to send the BGP Update messages to the GRPC Server which runs on port 50051. The .proto file is provided and you only need to compile and use the `queryMformat` function with the provided format:

```
message MformatMessage {
  string service = 1;
  string type = 2;
  string prefix = 3;
  repeated int32 as_path = 4;
  double timestamp = 5;
}
```

For example take a look at the `taps/exabgp_client.py` which implements the python GRPC Client or `taps/ripe_ris.js` which implements the javascript GRPC Client. Please edit only the code in the taps folder.

## Versioning
TBD (for now working on the bleeding edge of the master branch, version tags to-be-released)

## Authors
* Dimitris Mavrommatis, FORTH-ICS
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
