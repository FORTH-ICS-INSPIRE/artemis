# ARTEMIS

ARTEMIS is a defense approach versus BGP prefix hijacking attacks (a) based on accurate and fast detection operated by the AS itself, leveraging the pervasiveness of publicly available BGP monitoring services and their recent shift towards real-time streaming, thus (b) enabling flexible and fast mitigation of hijacking events. Compared to existing approaches/tools, ARTEMIS combines characteristics desirable to network operators such as comprehensiveness, accuracy, speed, privacy, and flexibility. With the ARTEMIS approach, prefix hijacking can be neutralized within a minute!

You can read more on INSPIRE Group ARTEMIS webpage: http://www.inspire.edu.gr/artemis

## Getting Started

These instructions will get you a copy of the ARTEMIS tool up and running on your local machine for testing purposes. For a detailed view of the ARTEMIS system architecture please check architecture.txt.

### Dependencies

* [Python 3](https://www.python.org/downloads/)   —  **ARTEMIS** requires Python 3.4.

Install pip3
```
sudo apt-get install python3-pip
```

Then inside the root folder of the tool run
```
pip3 install -r requirements.txt
```

For RIPE RIS monitors you need to install nodejs
```
curl -sL https://deb.nodesource.com/setup_9.x | sudo -E bash -
sudo apt-get install -y nodejs build-essential
```

Then install the needed modules
```
cd taps
npm install
```

For BGPStream live support (as well as historical data retrieval), you need to follow the
instructions on:
```
https://bgpstream.caida.org/docs/install/bgpstream
https://bgpstream.caida.org/docs/install/pybgpstream
```
in order to install the libbgpstream (core) and the Python library/API pybgpstream

Since pybgpstream requires python2, you need to install also:
```
pip2 install --user grpcio==1.10.0
pip2 install --user grpcio-tools==1.10.0
pip2 install --user protobuf==3.5.2
pip2 install --user protobuf3-to-dict==0.1.5
```

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

Note: to run the mininet demo please follow the instructions under mininet-demo/README.md

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
* Dimitris Mavrommatis, ICS-FORTH
* Petros Gigis, ICS-FORTH
* Vasileios Kotronis, ICS-FORTH
* Pavlos Sermpezis, ICS-FORTH

## License
TBD (closed source until further notice)

## Acknowledgments
TBD (ERC NetVolution Grant, ERC PoC Grant, RIPE NCC Community Project Grant)
