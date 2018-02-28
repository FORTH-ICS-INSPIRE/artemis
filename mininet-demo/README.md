# Before you begin
The following demo has been tested on an Ubuntu Server 16.04 VM

# installation

## install artemis
see README 1 level up

## install requirements
sudo apt-get install python3-pip -y

sudo apt-get install python-pip -y

pip3 install -r requirements.txt

pip install -r requirements.txt

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
cd ~

git clone https://github.com/mininet/mininet

cd mininet; git checkout 2.2.2

./util/install.sh -fnv

# running the demo

## switch to the mininet-demo folder
cd ~/artemis-tool/mininet-demo

## configure artemis accordingly
vim ../configs/config

## configure the exabgp collectors with the absolute path to exabgp_server.py (under taps folder)
vim ./configs_policy/exabgp-6500*.conf

## run mininet topology (shown on artemis_ascii_topo_policy.txt)
sudo ./artemis-topo-policy.py

ASNs: 65001 (victim), 65004 (hijacker), 65005 (helper), 65002, 65003 (intermediate)

## fire up terminals
mininet> xterm artemis h1 h3 h4 R4 R5

## fire up artemis
artemis> cd ..; python3 artemis.py

## monitor traffic destined to h1 (in victim AS)
h1> tcpdump -ni h1-eth0 icmp

## monitor traffic destined to h4 (in hijacker AS)
h4> tcpdump -ni h4-eth0 icmp

## ping continuously 10.0.0.100 from h3 (in intermediate AS)
h3> ping 10.0.0.100

normal operation: h1 sees traffic

hijack operation: h4 sees traffic (and not h1)

## (optionally) activate MOAS daemon on R5 (in helper AS)
R5> cd ../routers/quagga; python moas_agent.py -li 0.0.0.0 -lp 3001 -la 65005

## configure R4 router to hijack /23 sub-prefix (deaggregatable)
R4> telnet localhost 2605

Password: sdnip (this is the password)

bgp> en (enable)

bgp# conf t (configure terminal)

bgp(config)# router bgp 65004

bgp(config-router)# network 10.0.0.0/23

## on artemis terminal, check detection + prefix deaggregation
artemis> (check output)

## on h1,h4 terminals, check that traffic is routed correctly
h1> (check output)

h4> (check output)

## traceroute from h3 (should flow normally to victim)
h3> traceroute 10.0.0.100

## configure R4 router to hijack /24 sub-prefix (non-deaggregatable)

bgp(config-router)# network 10.0.0.0/24

## on artemis terminal, check detection + MOAS notification
artemis> (check output)

## on R5 terminal, check MOAS mitigation
R5> (check output)

## on h1,h4 terminals, check that traffic is routed correctly
h1> (check output)

h4> (check output)

## traceroute from h3 (should flow over helper tunnel to victim)
h3> traceroute 10.0.0.100

## clean-up
mininet> exit

host> sudo mn -c




