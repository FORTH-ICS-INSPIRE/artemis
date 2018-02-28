# ARTEMIS

ARTEMIS is a defense approach versus BGP prefix hijacking attacks (a) based on accurate and fast detection operated by the AS itself, leveraging the pervasiveness of publicly available BGP monitoring services and their recent shift towards real-time streaming, thus (b) enabling flexible and fast mitigation of hijacking events. Compared to existing approaches/tools, ARTEMIS combines characteristics desirable to network operators such as comprehensiveness, accuracy, speed, privacy, and flexibility. With the ARTEMIS approach, prefix hijacking can be neutralized within a minute!

You can read more on INSPIRE Group ARTEMIS webpage: http://www.inspire.edu.gr/artemis

## Getting Started

These instructions will get you a copy of the ARTEMIS tool up and running on your local machine for testing purposes.

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
### How to run

To succesfully run the script you need to modify the configuration file

```
cd configs/config
```

After modifying the configuration file run

```
python3 artemis.py
```

Note: to run the mininet demo please follow the instructions under mininet-demo/README.md


## Contributing


## Versioning


## Authors


## License



## Acknowledgments

