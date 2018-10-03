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

## Min. technical requirements of testing server/VM

* CPU: 4 cores
* RAM: 4 GB
* HDD: 100 GB
* NETWORK: 1 public-facing network interface
* OS: Ubuntu Linux 16.04+
* SW PACKAGES: docker-ce and docker-compose should be pre-installed
and docker should have sudo privileges, if only non-sudo user is allowed
* Other: SSH server

Moreover, one needs to configure firewall rules related to the testing server/VM.
We recommend using [ufw](https://www.digitalocean.com/community/tutorials/how-to-set-up-a-firewall-with-ufw-on-ubuntu-16-04)
for this task. Please check the comments in the respective script we provide and
set the corresponding <> fields in the file before running:
```
sudo ./other/ufw_setup.sh
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
Before starting ARTEMIS, you should configure access to the web application
(used to configure/control ARTEMIS and view its state),
by editing the following file:
```
docker-compose.yml
```
and adjusting the following parameters/environment variables related
to the artemis_frontend container:
```
USER_ROOT_USERNAME: "admin"
USER_ROOT_PASSWORD: "admin"
USER_ROOT_EMAIL: "admin@admin"
```
The ARTEMIS web application supports https to ensure secure access to the application.
We use a nginx reverse proxy to terminate SSL connections before forwarding the requests
to Flask. To configure your own certificates, please place in the following folder:
```
frontend/webapp/configs/certs
```
the following files:
```
cert.pem
key.pem
```
You do not need to modify any other configuration file for now.

### Configuring logging (syslog)
You should edit the following file:
```
docker-compose.yml
```
and adjust the following environment variables:
```
SYSLOG_HOST=<IP>:<PORT>
```
in the environment variable section of
the artemis_frontend and artemis_backend services.
Note that setting this to anything other than the default is under testing.

### Starting ARTEMIS
You can now start ARTEMIS as a multi-container application
by running:
```
docker-compose up
```
in interactive mode, or:
```
docker-compose up -d
```
in detached mode (to run it as a daemon).

### Using the web application
Visually, you can now configure, control and view ARTEMIS on https://<ARTEMIS_HOST>.

*Note*: Please use only the web application forms to configure ARTEMIS.

### Registering users (ADMIN/VIEWER)
```
https://<ARTEMIS_HOST>/create_account
```
Here you can input your credentials and request a new account. The new account has to be approved
by an ADMIN user. The default role for new users is VIEWER.

### Managing users (ADMIN-only)
```
https://<ARTEMIS_HOST>/admin/user_management
```
Here the ADMIN user can approve pending users, promote users to admins, as well as delete users.
An ADMIN can delete VIEWER users, but not ADMIN users.

### User account actions (ADMIN-VIEWER)
Currently the current account-specific actions are supported:
* Password change (TBD)
* ... (TBD)

### Configuring and Controlling ARTEMIS through the web application (ADMIN-only)
```
https://<ARTEMIS_HOST>/admin/system
```
Here the ADMIN may switch the Monitor, Detection and Mitigation modules of ARTEMIS on and off,
as well as edit the configuration. The configuration file has the following (yaml) format:
```
#
# ARTEMIS Configuration File
#

# Start of Prefix Definitions
prefixes:
  <prefix_group_1>: &prefix_group_1
    - <prefix_1>
    - <prefix_2>
    - ...
    - <prefix_N>
  ...: &...
    - ...
# End of Prefix Definitions

# Start of Monitor Definitions
monitors:
  riperis: ['']
  bgpstreamlive:
    - routeviews
    - ris
  exabgp:
    - ip: <IP_1>
      port: <PORT_1>
    - ip: ...
      port: ...
  # bgpstreamhist: <path_to_csv_dir>
# End of Monitor Definitions

# Start of ASN Definitions
asns:
  <asn_group_1>: &asn_group_1
    - <asn_1>
    - ...
    - <asn_N>
  ...: &...
    - ...
    - ...
# End of ASN Definitions

# Start of Rule Definitions
rules:
- prefixes:
  - *<prefix_group_k>
  - *...
  origin_asns:
  - *<asn_group_j>
  - *...
  neighbors:
  - *<asn_group_l>
  - *...
  mitigation:
    manual
- ...
# End of Rule Definitions
```

### Viewing ARTEMIS state
After being successfully logged-in to ARTEMIS, you will be redirected to the following webpage:
```
https://<ARTEMIS_HOST>/admin/system
```
Here you can view info about:
* your last login information (time and IP address)
* the system status (status of modules and uptime information)
* the current configuration of the system (and its last update time)
* the ARTEMIS version you are running
* statistics about the ARTEMIS db, in particular:
** Total number of BGP updates, as well as of unhandled (by the detection) updates
** Total number of detected BGP hijacks (as well as a break-down in "resolved",
"under mitigation", "ognoing" and "ignored").

### Viewing BGP updates
All BGP updates captured by the monitoring system in real-time can be seen here:
```
https://<ARTEMIS_HOST>/main/bgpupdates/
```
The following fields are supported:
* ID (DB-related)
* Prefix (IPv4/IPv6)
* Origin AS
* AS Path (only for BGP announcements)
* Peer AS (from where the information was learned)
* Service, in the format <data_source>|<collector_name>
* Type (A|W - Announcement|Withdrawal)
* Timestamp (displayed in local time zone)
* Hijack (if present, redirects to a corresponding Hijack entry)
* Status (blue if the detector has seen the update, grey if examination is pending)
* Additional information: Communities ([{'asn':..., 'value':...}, ...])
* Additional information: Original Path (if the original path e.g., contains AS-SETs, etc.)
* Additional information: Hijack Key (unique hijack identifier)

You can sort the BGP updates table by the ID, Prefix, Origin AS, AS Path, Peer AS, Service, Type and
Timestamp fields. The information is paginated and the number of shown entries is tunable.
You can further select updates related to a certain configured prefix (or all prefixes related to your network),
as well as based on a tunable time window.

### Viewing BGP hijacks
All BGP hijacks detected by the detection system in real-time can be seen here:
```
https://<ARTEMIS_HOST>/main/hijacks/
```
The following fields are supported:
* ID (DB-related)
* Status (ongoing|under mitigation|ignored|resolved)
* Prefix (IPv4/IPv6)
* Type (S - Subprefix|Q - Squatting|0 - Origin|1 - fake first hop)
* Hijack AS (-1 for Type-S hijacks)
* Number of Peers Seen (the ones that have seen the event)
* Number of ASes Infected (the ones that seemingly route to the hijacker)
* Time Started (when the event actually started)
* Additional information: Time Ended (this is set only for resolved hijacks)
* Additional information: Hijack Key (unique hijack identifier)
* Additional information: Mitigation Started (this is set only for hijacks under mitigation)
* Additional information: Matched Prefix (the prefix that best matched configuration, if applicable)
* Additional information: Config Matched (the timestamp of the configuration against which the hijack was generated)
* Additional information: Time Detected (the timestamp when the hijack was actually detected)

You can sort the BGP hijacks table by the ID, Status, Prefix, Type, Hijack AS, Number of Peers Seen,
Number of ASes Infected and Time Started fields. The information is paginated and the number of shown entries is tunable.
You can further select hijacks related to a certain configured prefix (or all prefixes related to your network),
as well as based on a tunable time window.

Note that after the details of a hijack, you can also see details on the BGP updates that triggered it.

### Actions on BGP hijacks (ADMIN-only)
The ADMIN user can use the following buttons:
* Resolve: The hijack has finished (by successful mitigation or other actions). It marks the Time Ended
field and sets an ongoing or under mitigation hijack to resolved state.
* Mitigate: Start the mitigation process for this hijack. It sets the Mitigation Started field and sets an ongoing
hijack to under mitigation state. Note that the mitigation module should be active for this to work.
* Ignore: the hijack is a false positive. It sets an ongoing or under mitigation hijack to ignored state.

Note that only the following state transitions are enabled:
* ongoing --> under mitigation
* ongoing --> resolved
* ongoing --> ignored
* under mitigation --> resolved
* under mitigation --> ignored

The VIEWER use can see the status of a hijack but cannot activate any buttons.

### CLI controls [optional]

You can also control ARTEMIS (if required) via a CLI, by executing the following command(s):
```
docker exec -it artemis python3 scripts/module_control.py -m <module> -a <action>
```
Note that module = all|configuration|scheduler|postgresql_db|monitor|detection|mitigation,
and action=start|stop|status.

Also note that the web application (frontend) and the backend operate in their own separate containers; to e.g.,
restart them, please run the following command:
```
docker-compose restart artemis_frontend
docker-compose restart artemis_backend
```

### Receiving BGP feed from local route reflector via exaBGP
For instructions on how to set up an exaBGP-based local monitor,
getting BGP updates' feed from your local router or route reflector,
please check [here](https://github.com/slowr/ExaBGP-Monitor)

In ARTEMIS, you should configure the monitor using the web application form in
```
https://<ARTEMIS_HOST>/admin/system
```
by setting its IP address and port. An example is the following:
```
...
monitors:
  ...
  exabgp:
    - ip: 192.168.1.1
      port: 5000
...
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
We are finalizing the process of open-sourcing the ARTEMIS software under the BSD-3 license.
A provisional [license](LICENSE) has been added to the code.
During the testing phase and until ARTEMIS is fully open-sourced, the tester is allowed to have access
to the code and use it, but is not allowed to disclose the code to third parties.

## Acknowledgements
This work is supported by the following sources:
* European Research Council (ERC) grant agreement no. 338402 (NetVolution Project)
* RIPE NCC Community Projects Fund
