# Technical Requirements

## Basic

ARTEMIS is a `docker` application that can run on a Linux server (or a Kubernetes cluster).

## Minimum Technical Requirements

* CPU: 4 cores
* RAM: 4+ GB (note that needed memory depends on the number of configured prefixes/rules/asns and load of incoming BGP updates, see [here](https://bgpartemis.readthedocs.io/en/latest/requirements/#memory-requirements) for more details)
* HDD: 50 GB (less may suffice, depending on the use case for storing BGP updates and hijack alerts)
* NETWORK: 1 public-facing network interface (optionally: one internal interface for connection with local route collectors)
* OS: Ubuntu Linux 16.04+ (other Linux distributions will work too)
* SW PACKAGES: `docker-ce` and `docker-compose` should be pre-installed (see instructions later) and `docker` should have sudo privileges, if only non-sudo user is allowed
* Other: `SSH` server

Moreover, one may optionally configure firewall rules related to the server/VM.
We recommend using [ufw](https://www.digitalocean.com/community/tutorials/how-to-set-up-a-firewall-with-ufw-on-ubuntu-16-04)
for this task. Please check the comments in the respective script we provide and
set the corresponding <> fields in the file before running:
```
sudo ./other/ufw_setup.sh
```
**NOTE: For security reasons, we highly recommend protecting your machine with such rules. ARTEMIS tries to minimize external port exposure to minimize the attack surface on the system itself.**

## Memory requirements

* 4G for the base version of ARTEMIS (one instance of each default microservice),
with an "average" configuration of some 100s of prefixes/rules.
Note though that this may vary depending on the form of the conf file:
e.g., if you have 100s of prefixes *and* 100s of rules *and* 10s of ASNs per rule,
these are essentially stored in the form of an (efficient) cross-product in RAM:
100x100x10 ~ 1 mil ~ 1GB requirements per `prefixtree` microservice that uses them.
* For each 1 mil extra elements (prefixes, rules, asns or combination of them) --> +1 GB per additional `prefixtree` instance.

For example, assuming a setup with one database, one monitor and one detector, and 2 million prefixes with a small
number of rules and ASNs per prefix (O(1)), you will need: 4 GB (base) + 3 x 2 x 1GB = 10 GB RAM (approximately, crude calculation). If you use an extra e.g., detector, you will need 2 GB additionally, and so on.

Therefore, with the "latest" ARTEMIS version users should be able to run ARTEMIS with a 10+G machine with no problem,
assuming an average O(1K-10K)-elements configuration file and the default numbers of `prefixtree` microservices
(one). Note that the incoming load of BGP updates stored in memory may also strain the RAM a bit, this is why we keep
the 4G as the absolutely basic requirement and add upon it depending on the user's configuration.
