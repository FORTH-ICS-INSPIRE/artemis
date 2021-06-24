#!/bin/sh
sudo apt update -y
sudo apt upgrade -y
apt install python3-pip -y
pip3 install netaddr
pip3 install ujson
apt install curl -y 
curl -s https://pkg.caida.org/os/$(lsb_release -si|awk '{print tolower($0)}')/bootstrap.sh | bash 
apt install bgpstream
pip3 install pybgpstream
