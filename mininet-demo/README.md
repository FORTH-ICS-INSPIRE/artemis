# installation
## install requirements
sudo apt-get install python3-pip -y

sudo -H pip3 install -r requirements.txt

## install exabgp
cd ~

sudo apt-get install git

git clone https://github.com/Exa-Networks/exabgp

cd exabgp; git checkout 3.4

echo 'export PATH=$PATH:~/exabgp/sbin' >> ~/.bashrc

source ~/.bashrc

## install quagga
cd ~

sudo apt-get install quagga -y

## install mininet
git clone https://github.com/mininet/mininet

cd mininet; git checkout 2.2.2

./util/install.sh -fnv

# running the demo

## configure exabgp with the path to exabgp-monitor.py
vim ./configs/exabgp.conf

## run mininet topology
sudo ./artemis-topo-policy.py

## configure R9 router to hijack prefix
R9> telnet localhost bgpd

Password: sdnip (this is the password)

bgp> en (enable)

bgp# conf t (configure terminal)

bgp(config)# router bgp 65009

bgp(config-router)# network 10.0.0.0/8
