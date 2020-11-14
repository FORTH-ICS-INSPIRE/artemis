# Overview

## The basic logic of ARTEMIS
ARTEMIS receives BGP update feeds from public or private monitors in real-time (streaming feed),
cross-checks their information against a local configuration file and makes a reliable inference about
a potential hijack event within seconds, enabling immediate mitigation.

The basic philosophy behind the extensible ARTEMIS software architecture is the use of a message bus (MBUS),
used for routing messages (RPC, pub/sub, etc.) between different micro-services
within and across containers, interfacing with the MBUS between message producers and consumers.

In a nutshell, we have the following micro-services:

* Configuration
* Monitoring
* Detection
* Mitigation
* DB access/management
* Clock
* Observer
* Listener/Supervisor
* User interface

The operator (i.e., the "user") interfaces with the system by filling in a configuration file
and by interacting with the web application (UI) to control the various micro-services and
see useful information related to monitoring entries and detected hijacks (including their
current status). Configuration is imported in all micro-services since it is used for monitor
filtering, detection tuning, mitigation configuration and other functions. The feed from
the monitoring micro-service (which can stem from multiple BGP monitoring sources around the world,
including local monitors) is validated and transmitted to the detection and db access micro-services.
The detection micro-service reasons about whether what it sees is a hijack or not; if it is, it
generates a hijack entry which is in turn stored in the DB, together with the corresponding
monitoring entries. Finally, using the web application, the operator can instruct the mitigation
micro-service to (un-)mitigate a hijack or mark it as resolved/ignored.
All information (configuration, updates, hijacks and micro-service state) is persistently
stored in the DB, which is accessed by the web application.
Clock, listener/supervisor and observer micro-services are auxiliary, and take care of periodic clock signaling, micro-service status change events and configuration change notifications, respectively. For brevity we do not elaborate more on further auxiliary micro-services. In case you are interested in more details please check the source code under backend/core or contact the ARTEMIS team.

## ARTEMIS Installation and Setup

### Install Packages

1. Make sure that your Ubuntu package sources are up-to-date:
   ```
   sudo apt-get update
   ```

2. **(For rootless installation look below)** If not already installed, follow the instructions [here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-docker-ce) to install the latest version of the docker tool for managing containers, and [here](https://docs.docker.com/compose/install/#install-compose) to install the docker-compose tool for supporting multi-container Docker applications.

   In production, we have used the following versions successfully:
   ```
   $ docker -v
   Docker version 18.09.0, build 4d60db4
   $ docker-compose -v
   docker-compose version 1.20.0, build ca8d3c6
   ```

3. If you would like to run docker without using sudo, please create a docker group, if not existing:
   ```
   sudo groupadd docker
   ```
   and then add the user to the docker group:
   ```
   sudo usermod -aG docker $USER
   ```
   For more instructions and potential debugging on this please consult this [webpage](https://docs.docker.com/install/linux/linux-postinstall/#manage-docker-as-a-non-root-user).

4. Install ntp for time synchronization:
   ```
   sudo apt-get install ntp
   ```

5. Install git for downloading ARTEMIS:
   ```
   sudo apt-get install git
   ```
   and then download ARTEMIS from github (if not already downloaded):
   ```
   git clone ...
   ```

6. The docker-compose utility is configured to pull the latest **stable** released images that are built remotely on [docker cloud](https://cloud.docker.com/). Run the following:
    ```
    cd artemis
    docker-compose pull
    ```
    to trigger this.

    No further installation/building actions are required on your side at this point.

### Rootless Docker

You can follow instructions on how to install rootless docker [here](https://docs.docker.com/engine/security/rootless/).

In our setup we used `slirp4netns` as the network stack and instead of ports 80 and 443 we remapped to 8080 and 8433 for avoid the need of binding with `sudo`.

You can change these values inside the `docker-compose.yaml`:
```
        ports:
            # uncomment both lines for rootless
            # - "8080:8080"
            # - "8443:8443"
            # comment both lines when running rootless
            - "80:80"
            - "443:443"
```

These changes should be sufficient to have artemis running rootless on `https://localhost:8443`.

### Setup Tool

1. Edit environment variables in .env file (especially the security-related variables); please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/envvars/) for more information on the env variables.
A comprehensive list of environment variables and their exact use can be found at [Environment variables](https://bgpartemis.readthedocs.io/en/latest/envvars/),
detailing all variables used in the .env file used for ARTEMIS system setup (non-hijack-related).

2. It is important that before starting ARTEMIS, you should setup secure access to the web application
   (used to configure/control ARTEMIS and view its state),
   by editing the following file:
   ```
   .env
   ```
   and adjusting the following parameters/environment variables related
   to the artemis_frontend:
   ```
   ADMIN_USER=admin
   ADMIN_PASS=admin123
   ADMIN_EMAIL=admin@admin
   ```
   and modifying the secrets for your own deployment (**critical**):
   ```
   JWT_SECRET_KEY
   FLASK_SECRET_KEY
   SECURITY_PASSWORD_SALT
   HASURA_SECRET_KEY
   ```
   Except for the `HASURA_SECRET_KEY`, which is a master password for the graphql queries, the other
   keys need to be randomly generated with the following command (generates 32 random bytes hexadecimal string):
   ```
   openssl rand -hex 32
   ```
   **NOTE: For security reasons, we highly recommend randomizing these keys (no defaults), and using strong passwords. Be careful with special characters in these fields as some of them need to be escaped and other are passed as URI.**

   **We suggest using HEX format or URL encoded passwords to avoid any issues.**

3. Decouple your setup files (tool configurations) from the default ones (that are under version control), by doing the following in your local artemis directory:
   ```
   mkdir -p local_configs && \
   mkdir -p local_configs/backend && \
   mkdir -p local_configs/monitor && \
   mkdir -p local_configs/frontend && \
   cp -rn backend/configs/* local_configs/backend && \
   cp -rn backend/supervisor.d local_configs/backend && \
   cp -rn monitor/configs/* local_configs/monitor && \
   cp -rn monitor/supervisor.d local_configs/monitor && \
   cp -rn frontend/webapp/configs/* local_configs/frontend
   ```
   and then change the source mappings in `docker-compose.yaml`, by following the instructions within the file.
   Example:
   ```
   # comment after Step 2 of README
   ```
   means: "comment out the following line"
   and:
   ```
   # uncomment after Step 2 of README
   ```
   means: "uncomment the following line".
   *You do not have to uncomment the lines: `- ./backend/:/root/`, `- ./monitor/:/root/` and `- ./frontend/:/root/` if you are NOT building from source.*

   The local_configs directory is NOT under version control.
   The same applies to:
   ```
   postgres-data-current
   postgres-data-backup
   frontend/db
   ```
   A sample folder structure for local_configs is the following:
   ```
   $ tree local_configs
   local_configs
   ├── backend
   │   ├── config.yaml
   │   ├── logging.yaml
   │   └── supervisor.d
   │       └── services.conf
   ├── frontend
   │   ├── certs
   │   │   ├── cert.pem
   │   │   └── key.pem
   │   ├── config.py
   │   ├── __init__.py
   │   ├── logging.yaml
   │   ├── nginx.conf
   │   └── webapp.cfg
   └── monitor
       ├── exabgp.conf
       ├── logging.yaml
       └── supervisor.d
           └── services.conf
   ```

4. Setup https: the ARTEMIS web application supports https to ensure secure access to the application. We use a nginx reverse proxy to terminate SSL connections before forwarding the requests to Flask. To configure your own (e.g., self-signed) certificates, please place in the following folder:
   ```
   local_configs/frontend/certs
   ```
   the following files:
   ```
   cert.pem
   key.pem
   ```
   If you want to use e.g., "let's encrypt" certificates you can do the following steps:
   1. edit the file:
      ```
      other/lets_encrypt.sh
      ```
      according to your setup, and then run it with sudo (after making sure it is executable).

   2. edit the nginx section of the file:
      ```
      docker-compose.yaml
      ```
      to include the following volume mappings instead of the default certs one (comment that one out):
      ```
      - /etc/letsencrypt/live/<domain>/fullchain.pem:/etc/nginx/certs/cert.pem
      - /etc/letsencrypt/live/<domain>/privkey.pem:/etc/nginx/certs/key.pem
      - /etc/letsencrypt/options-ssl-nginx.conf:/etc/nginx/options-ssl-nginx.conf
      - /etc/letsencrypt/ssl-dhparams.pem:/etc/nginx/ssl-dhparams.pem
      ```

   3. edit the nginx configuration file:
      ```
      local_configs/frontend/nginx.conf
      ```
      to include the following lines:
      ```
      ssl_dhparam /etc/nginx/ssl-dhparams.pem;
      include /etc/nginx/options-ssl-nginx.conf;
      ```

   Also, if you require selective access to the UI from certain IP ranges, please adjust and comment out the nginx ACL-related lines in:
   ```
   local_configs/frontend/nginx.conf
   ```
   **NOTE: For security reasons, we highly recommend replacing the default certificates, as well as restricting access to the nginx server.**

5. Setup logging and access to ARTEMIS logs, by checking the corresponding [docs page](https://bgpartemis.readthedocs.io/en/latest/loggingconf/).

You do not need to modify any other setup files and variables for now.
Optionally, you may edit the file:
```
local_configs/frontend/webapp.cfg
```
to circumvent other default parameters used in the frontend.
These parameters and their explanation can be found at [Additional frontend env variables](https://bgpartemis.readthedocs.io/en/latest/frontendconf/).

## Starting ARTEMIS
You can now start ARTEMIS as a multi-container application by running:
```
docker-compose up -d
```
or if you want additional services:
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml up -d
```
runs in detached mode (-d, to run it as a daemon; recommended mode).

**RECOMMENDATION: After starting ARTEMIS, always check the logs by running:**
```
docker-compose logs
```
**or**:
```
docker-compose -f ... logs
```
**The addition of a -f flag after the logs keyword will provide you running logs.
Checking them is important to see if something went wrong. Consult also [ARTEMIS-logging](https://bgpartemis.readthedocs.io/en/latest/loggingconf/)**.
If everything went ok you will see an output as follows (may differ if you open up the UI in parallel):
```
rabbitmq          | 2019-02-27 09:01:11.342 [info] <0.738.0> accepting AMQP connection <0.738.0> (172.21.0.4:43494 -> 172.21.0.2:5672)
rabbitmq          | 2019-02-27 09:01:11.344 [info] <0.738.0> connection <0.738.0> (172.21.0.4:43494 -> 172.21.0.2:5672): user 'guest' authenticated and granted access to vhost '/'
rabbitmq          | 2019-02-27 09:01:11.371 [info] <0.752.0> accepting AMQP connection <0.752.0> (172.21.0.4:43496 -> 172.21.0.2:5672)
rabbitmq          | 2019-02-27 09:01:11.374 [info] <0.752.0> connection <0.752.0> (172.21.0.4:43496 -> 172.21.0.2:5672): user 'guest' authenticated and granted access to vhost '/'
backend           | database - 2019-02-27 09:01:11,387 - INFO @ __init__: started
rabbitmq          | 2019-02-27 09:01:11.404 [info] <0.763.0> accepting AMQP connection <0.763.0> (172.21.0.4:43498 -> 172.21.0.2:5672)
rabbitmq          | 2019-02-27 09:01:11.411 [info] <0.763.0> connection <0.763.0> (172.21.0.4:43498 -> 172.21.0.2:5672): user 'guest' authenticated and granted access to vhost '/'
```

Extra services that you can use with ARTEMIS are:

* exabgp: local exaBGP monitor
* grafana: visual interfaces/dashboards; please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/grafanadash/)

*Note that while the bleeding-edge backend, monitor and frontend code is available in the repository, docker-compose is configured to pull the latest **stable** released images that are built remotely on [docker cloud](https://cloud.docker.com/). Optionally, you can run ARTEMIS with your own local code copy by uncommenting the following lines in docker-compose.yaml:*
```
## - ./backend/:/root/
## - ./monitor/:/root/
## - ./frontend/:/root/
```
*and then running as described above.*

## Using the web application
Visually, you can now configure, control and view ARTEMIS by logging in to https://<ARTEMIS_HOST>/login.
The default ADMIN user can login with the credentials set in the .env variables.

We recommend that you use the latest version of Chrome for the best ARTEMIS experience.

## Registering users
```
https://<ARTEMIS_HOST>/create_account
```
Here you can input your credentials and request a new account. The new account has to be approved
by an ADMIN user. The default role for new users is VIEWER.

## Managing users
```
https://<ARTEMIS_HOST>/admin/user_management
```
Here the ADMIN user can approve pending users,
promote users to admins, demote users from admins,
delete users and view all users.
An ADMIN can delete VIEWER users, but not ADMIN users
(these need to be demoted first; except for the root admin
user who can never be demoted and thus deleted for availability
reasons).

## User account actions (ADMIN-VIEWER)
Currently the current account-specific actions are supported:

* Password change at:
```
https://<ARTEMIS_HOST>/actions/password_change
```

## Configuring and Controlling ARTEMIS through the web application
```
https://<ARTEMIS_HOST>/admin/system
```
Here the ADMIN may switch the Monitor, Detection and Mitigation micro-services of ARTEMIS on and off,
as well as edit the configuration. The configuration file has the following (yaml) format (**please check
[this page](https://bgpartemis.readthedocs.io/en/latest/basicconf/) for details on the different sections**; note that reserved words are marked in bold):

```
#
## ARTEMIS Configuration File
#
#
## Start of Prefix Definitions
prefixes:
  <prefix_group_1>: &prefix_group_1
    - <prefix_1>
    - <prefix_2>
    - ...
    - <prefix_N>
  ...: &...
    - ...
## End of Prefix Definitions
#
## Start of Monitor Definitions
monitors:
  riperis: ['']
  bgpstreamlive:
      - routeviews
      - ris
      - caida
  exabgp:
      - ip: <IP_1>
        port: <PORT_1>
  #     - ip: ...
  #       port: ...
  # bgpstreamhist: <path_to_csv_dir>
## End of Monitor Definitions
#
## Start of ASN Definitions
asns:
  <asn_group_1>: &asn_group_1
    - <asn_1>
    - ...
    - <asn_N>
  ...: &...
    - ...
    - ...
## End of ASN Definitions
#
## Start of Rule Definitions
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
## End of Rule Definitions
```

Optionally the user can accompany the configuration with comments.

Note that the colors of the controllable modules are as follows:

* red: the micro-service is off (due to administrative action).
* yellow: the micro-service is (re)loading due to a configuration change (or upon boot).
* green: the micro-service is up and running, ready to operate (and its configuration has been loaded).

## Viewing ARTEMIS Configurations
```
https://<ARTEMIS_HOST>/main/config_comparison
```
Here the user (ADMIN|VIEWER) can view the ARTEMIS configuration history and diffs, as well as the (optional) comments attached to each configuration. Since configuration changes are atomic operations, the different configurations are keyed with their modification timestamp.

## Viewing ARTEMIS state
After being successfully logged-in to ARTEMIS, you will be redirected to the following webpage:
```
https://<ARTEMIS_HOST>/overview
```
Here you can view info about:

* your last login information (email address, time and IP address)
* the system status (status of micro-services and uptime information). In particular, colors mean the following:
  * red: the micro-service is off (due to administrative action or because it has failed).
  * yellow: the micro-service is (re)loading due to a configuration change (or upon boot).
  * green: the micro-service is up and running, ready to operate (and its configuration has been loaded).
* most recent ongoing (non-dormant) BGP hijacks related to your network's prefixes
* the ARTEMIS version you are running
* statistics about the ARTEMIS db, in particular:
  * Total number of configured prefixes
  * Total number of monitored prefixes (note that ARTEMIS needs to monitor only the super-prefix if it covers more than one sub-prefixes, so this number is always smaller than or equal to the number of configured prefixes)
  * Total number of monitored peers (that peer with route collector services and have observed at least one BGP update during the tool's lifetime)
  * Total number of BGP updates, as well as of unhandled (by the detection micro-service) updates
  * Total number of detected BGP hijacks (as well as a break-down in "resolved",
"under mitigation", "ongoing", "dormant", "withdrawn", "outdated", "ignored" and "seen").

Please use the embedded mouse-hover info for more information on the fields.

## Viewing BGP Updates
All BGP updates captured by the monitoring system in real-time can be seen here:
```
https://<ARTEMIS_HOST>/main/bgpupdates/
```
For information on the fields, please check [BGP update information](https://bgpartemis.readthedocs.io/en/latest/bgpupdateinfo/).

You can use the embedded mouse-hover tooltip for more information on the fields.
*Note: since the underlying data might change live, we recommend deactivating "live update" (button on the top right of the page) in case you would like to examine the content of a mouse-hover (e.g., related to a certain ASN) without it disappearing upon change. Remember to activate it again after the check!*

Regarding the BGP Updates table, the following auxiliary actions are supported:
* (De)activate "Live Update" via the button at the top right of the page.
* Select past time threshold for viewing BGP updates, based on their *Timestamp* field using the controls at the top left of the page (Past 1h,..,Custom).
* Download current (filtered or not) table in json format using the *Download Table* button at the top right of the page.
* Tune the number of shown BGP update entries using the control *Show* at the top left of the page.
* Select the configured prefix that you want to filter the BGP updates against (sub-prefixes are also accounted for) using the control *Select prefix* at the top left of the page.
* Use the filters on *Prefix*, *Origin AS*, *Peer AS*, *Service* and *Type* to filter the BGP updates against, using the empty fields under the table.
* Display all distinct values for the prefixes, origins, peers and services that are present in the BGP updates.
* Get information on the current timezone based on which timestamps are displayed at the bottom right of the table.

## Viewing and acting on BGP Hijacks
All BGP hijacks detected by the detection system in real-time can be seen here:
```
https://<ARTEMIS_HOST>/main/hijacks/
```
Specific hijacks can be examined by pressing "View" under the "More" tab, redirecting to a webpage of the following form:
```
https://<ARTEMIS_HOST>/main/hijack?key=....
```
For information on the fields, state and actions please check [Hijacks, States and Actions](https://bgpartemis.readthedocs.io/en/latest/hijackinfo/).

You can use the embedded mouse-hover tooltip for more information on the fields, states and actions. *Note: since the underlying data might change live, we recommend deactivating "live update" (button on the top right of the page) in case you would like to examine the content of a mouse-hover (e.g., related to a certain ASN) without it disappearing upon change. Remember to activate it again after the check!*

Regarding the Hijacks table, the following auxiliary actions are supported:

* Select and perform actions on multiple hijacks using the control above the table (Apply/Clear).
* (De)activate "Live Update" via the button at the top right of the page.
* Select past time threshold for viewing Hijacks, based on their Time Detected field using the controls at the top left of the page (Past 1h,..,Custom).
* Download current (filtered or not) table in json format using the Download Table button at the top right of the page.
* Tune the number of shown hijack entries using the control Show at the top left of the page.
* Select the configured prefix that you want to filter the hijacks against (sub-prefixes are also accounted for) using the control Select prefix at the top left of the page.
* Use the filters on Prefix, Type and Hijacker AS to filter the hijacks against, using the empty fields under the table.
* Display all distinct values for the prefixes and hijacker ASes that are present in the hijacks.
* Get information on the current timezone based on which timestamps are displayed at the bottom right of the table.

## Invoking multiple detectors/db clients [optional]
You can instruct the tool to run multiple instances of the detector/database micro-service in the supervisor's configuration. To do this you should modify the detection section in the configuration file that is located at `local_configs/backend/supervisor.d/services.conf`. A simple example to initiate 4 detection instances:
```
[program:detection]
process_name=%(program_name)s_%(process_num)02d
numprocs=4
```
or for database:
```
[program:database]
process_name=%(program_name)s_%(process_num)02d
numprocs=4
```
For more information on the Supervisor configuration please visit [Supervisor documentation](http://supervisord.org/).

**NOTE**: Always use a single '_' character to separate process name from its index.

## CLI controls [optional]
You can also control ARTEMIS micro-services (if required) via CLI, by executing the following command(s):
```
docker-compose exec backend bash
supervisorctl <action> <micro-service>
```
Note that micro-service = configuration|clock|database|detection|observer|listener|mitigation,
and action=start|stop|restart|status. Monitors are controlled by their own supervisor in their own separate container.

Also note that the web application (frontend), monitor and the backend operate in their own separate containers;
to e.g., restart them separately, please run the following command:
```
docker-compose restart frontend
docker-compose restart backend
docker-compose restart monitor
```

## Receiving BGP feed from local router/route reflector/BGP monitor via exaBGP

### Configuration

Change the following source mapping from [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.exabgp.yaml#L11) to:
```
- ./local_configs/monitor/exabgp.conf:/home/config/exabgp.conf
```
Edit the local_configs/monitor/exabgp.conf file as follows:
```
group r1 {
    router-id <PUBLIC_IP>; # the public IP of your ARTEMIS host

    process message-logger {
        encoder json;
        receive {
            parsed;
            update;
            neighbor-changes;
        }
        run /usr/lib/python2.7.14/bin/python /home/server.py;
    }

    neighbor <NEIGHBOR_IP> { # the IP of your BGP router/etc.
        local-address <LOCAL_LAN_IP>; # the local LAN IP of your ARTEMIS host
        local-as <LOCAL_ASN>; # the local (private) exaBGP monitor ASN that you will use for peering
        peer-as <PEER_ASN>; # your ASN from which the exaBGP monitor will receive the feed
    }
}
```
Stop the current ARTEMIS instance:
```
docker-compose stop
```
Start ARTEMIS with ExaBGP enabled:
```
docker-compose -f docker-compose.yaml -f docker-compose.exabgp.yaml up -d
```
Login to the UI and configure the monitor using the web application form in
```
https://<ARTEMIS_HOST>/admin/system
```
by setting its IP address and port. An example is the following:
```
...
monitors:
  ...
  exabgp:
    - ip: exabgp # this will automatically be resolved to the exabgp container's IP
      port: 5000 # default port
...
```
### Notes

1. We strongly recommend the use of eBGP instead of iBGP sessions between the
exaBGP monitor and the local router(s), in order to have information that can be better
used by the detection system.

2. Since the exaBGP container is one layer behind the networking
stack of the ARTEMIS host, establishing a successful eBGP connection between your router and
exaBGP will require properly setting the ebgp-multihop attribute on your router, e.g.,**

   ```
   >router bgp <my_as>
   >neighbor <exabgp_public_ip> ebgp-multihop 2 # if the router is one physical hop away
   ```

3. For all options on how to properly configure exaBGP, please visit [this page](https://manpages.debian.org/testing/exabgp/exabgp.conf.5.en.html).
Some useful options are the following:

   ```
   # within the neighbor section to set up md5 passwords
   md5-password <md5-secret>;

   # within the neighbor section to set up both v4 and  v6 advertisements
   family {
        ipv4 unicast;
        ipv6 unicast;
   }

   # the following section goes before the neighbor section to add a route refresh capability
   # needed to retrieve all prefixes from neighbor routers on monitor startup
   capability {
       route-refresh enable;
   }
   ```

## Replaying history
ARTEMIS can optionally replay historical records downloaded via tools like BGPStream.
The following steps need to be done for ARTEMIS to replay these records in a streaming fashion:

* Set the .env variable "HISTORIC" to true and restart ARTEMIS.
* Collect the files with the BGP updates in a csv directory. Each file should have the following bgpstream-compatible format:
  ```
  <prefix>|<origin_asn>|<peer_asn>|<blank_separated_as_path>|<project>|<collector>|<update_type_A_or_W>|<bgpstream_community_json_dump>|<timestamp>
  ```
  Note that withdrawal ('W') updates do not need to have the origin asn and as path specified (these can be empty strings), while 'A' updates require all fields. The format for community json dumps is as follows:
  ```
  [
    {
      'asn': <asn>,
      'value': <value>
    },
    ...
  ]
  ```
  *For convenience, we have published a [bgpstream-to-csv parser/converter](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/other/bgpstream_retrieve_prefix_records.py) which you can use as follows*:
  ```
  ./other/bgpstream_retrieve_prefix_records.py -p PREFIX -s START_TIME -e END_TIME -o OUTPUT_DIR
  arguments:
  -h, --help                          show this help message and exit
  -p PREFIX, --prefix PREFIX          prefix to check
  -s START_TIME, --start START_TIME   start timestamp (in UNIX epochs)
  -e END_TIME, --end END_TIME         end timestamp (in UNIX epochs)
  -o OUTPUT_DIR, --out_dir OUTPUT_DIR output dir to store the retrieved information
  ```
   Note that you will need the [bgpstream](https://bgpstream.caida.org/docs/install/bgpstream) and [pybgpstream](https://bgpstream.caida.org/docs/install/pybgpstream) and their dependencies installed locally to operate the script. Alternatively, you can map the script in a monitor volume in `docker-compose.yaml` and run it from within the monitor container, after also having properly mapped the directory where the output (i.e., the csvs with the BGP update records) will be stored.
* Stop ARTEMIS
* In docker-compose, in the monitor container mappings, map the directory containing the csv files to a proper monitor location, e.g.,:
  ```
  volumes:
      ... # other mappings
      - ./csv_dir/:/tmp/csv_dir/
      ... # other mappings
   ```
* Start ARTEMIS normally
* Edit ARTEMIS configuration to use the extra monitor:
  ```
  monitors:
    ... # other monitors (optional)
    bgpstreamhist: /tmp/csv_dir
  ```
* Activate monitoring and other modules if required

## GraphQL API
Please check [GraphQL API](https://bgpartemis.readthedocs.io/en/latest/graphqlapi/).

## Configuring backups

You can enable daily backups by changing the `DB_BACKUP` environment variable inside `.env` to true:
```
DB_BACKUP=true
```
The DB will then be regularly backed up (daily) in folder postgres-data-backup.

Restoring a backed up DB: Please check [Restoring DB from backup](https://bgpartemis.readthedocs.io/en/latest/dbrestore/).

## Auto-clean non-hijack BGP Updates

You can decide if you want to delete all old unwanted (non-hijack) BGP updates by setting the `DB_AUTOCLEAN` environment variable; this marks a time window (in hours) in which ARTEMIS keeps benign BGP updates. E.g.,
```
DB_AUTOCLEAN=24
```
means that any non-hijack updates older than 24 hours will be deleted by the system.
The default value is false (no deletion).

## Stopping and exiting ARTEMIS

Note that to gracefully terminate ARTEMIS and all its services you can use the following command:
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml stop
```
If you want to remove the containers as well: (**warning**: whatever file/directory is not properly mapped to a persistent local file/directory will be erased after container tear-down):
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml down
```
In case you do not use any extra services during composition, you can simply use:
```
docker-compose stop
docker-compose down
```
respectively.

## Upgrading ARTEMIS to a new version

### Main steps

Before upgrading, we recommend that you ensure that there is a recent (at most a day old) backup db.tar of the database under postgres-data-backup.
Then, do the following:

1. Make sure you have copied the default configs directories under local_configs and have updated the source volume mappings accordingly; check [this file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml) carefully for `local_configs` mappings. A sample folder structure for local_configs is the following:

   ```
   $ tree local_configs
   local_configs
   ├── backend
   │   ├── config.yaml
   │   ├── logging.yaml
   │   └── supervisor.d
   │       └── services.conf
   ├── frontend
   │   ├── certs
   │   │   ├── cert.pem
   │   │   └── key.pem
   │   ├── config.py
   │   ├── __init__.py
   │   ├── logging.yaml
   │   ├── nginx.conf
   │   └── webapp.cfg
   └── monitor
       ├── exabgp.conf
       ├── logging.yaml
       └── supervisor.d
           └── services.conf
   ```

2. Deactivate current running instance:

   ```
   docker-compose -f ... down
   ```

3. Stash any local changes that should not conflict with upstream

   ```
   git stash
   ```

4. Checkout the master  branch

   ```
   git checkout master
   ```

5. Pull most recent code (including .env, versions, etc.)

   ```
   git pull origin master
   ```

6. Re-apply local changes (if auto-merge fails, resolve any conflicts)

   ```
   git stash pop
   ```

7. **Make sure that you also do a**
   ```
   docker-compose -f ... pull
   ```
   **to ensure that you are not running an outdated version of the tool's containers.**

You are all set! Now you can boot ARTEMIS (`docker-compose -f ... up -d`).

### Notes

To work on a specific release the master code and the release version need to be compatible.
Therefore, if you do not want to have access to the latest code, but work on a previous stable release, you need to do:
```
git checkout tags/<release_id>
```
instead of step 5. This will automatically set the
SYSTEM_VERSION in the .env file to "release-XXXX", and sync the DB_VERSION. Always upgrade, never downgrade! A `docker-compose ... pull` will still be required.

Note that to avoid merge conflicts in general,
we recommend decoupling your local configurations from the upstream changes.
However, we would recommend keeping an eye out for any upstream changes that are related
to best practices for the configuration files.

*WARNING: If the change requires a DB upgrade (will be noted in the release), please check the next
section before doing:*
```
docker-compose -f ... up -d
```

**OPTIONAL**: If you want to change things at your local source code, and need to build your custom
frontend and backend containers (instead of pre-built images), you can use the following lines instead of `image: ...` (for backend, frontend and monitor containers, respectively):
```
build: ./backend
build: ./frontend
build: ./monitor
```
Note also that you need to always map your volumes properly (e.g., `./backend:/root/....`, etc.).
Custom building can be triggered with:
```
docker-compose -f ... build
```
*Note that for the frontend, you need to make sure that the js-compiled files are properly generated. You may need to copy them from a pre-built frontend container to be user. More details to follow (this refers only to custom builds that require changes to the frontend).*

**Also note that Kubernetes/helm upgrades may require a slightly different process, based on deployment upgrade.
For more details please ping us on slack or describe your experience in a GitHub issue.**

## Migrating an existing DB to a new version
While developing ARTEMIS, we may also need to change the DB schema.
In general, we aim to always remain backwards compatible; however
you will probably *not be able to run new code on an old schema*.
For this reason, we have developed an automated migration process that takes
care of such migrations.
To migrate to a new DB state that is in sync with the current code, simply execute the
ARTEMIS version upgrade workflow (see previous section).
If everything rolled down correctly (according to the logs), you will see that the migration process was successful
and ARTEMIS will be able to start correctly with "up -d".
If something fails, please contact the ARTEMIS team.

## Adding new ARTEMIS tests
The following [file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/backend/testing/messages.json) needs to be updated. Details to follow.

## Kubernetes deployment
Please check [Kubernetes Deployment](https://bgpartemis.readthedocs.io/en/latest/kubernetes/).

## Memory requirements
* 4G for the base version of ARTEMIS (one database module, one monitor, one detector, one mitigator), with an "average" configuration of some 100s of prefixes/rules. Note though that this may vary depending on the form of the conf file: e.g., if you have 100s of prefixes *and* 100s of rules *and* 10s of ASNs per rule, these are essentially stored in the form of an (efficient) cross-product in RAM: 100x100x10 ~ 1 mil ~ 1GB requirements per module that uses them.
* For each 1 mil extra elements (prefixes, rules, asns or combination of them) --> +1 GB per module (database, detector, monitor, mitigator).
* Each extra module (e.g., additional detectors/database modules) --> +1 GB (for each million of elements)

For example, assuming a setup with one database, one monitor and one detector, and 2 million prefixes with a small
number of rules and ASNs per prefix (O(1)), you will need: 4 GB (base) + 3 x 2 x 1GB = 10 GB RAM (approximately, crude calculation). If you use an extra e.g., detector, you will need 2 GB additionally, and so on.

Therefore, with the "latest" ARTEMIS version users should be able to run ARTEMIS with a 10+G machine with no problem,
assuming an average O(1K-10K)-elements configuration file and the default numbers of modules (1 monitor/detector/mitigator/database). Note that the incoming load of BGP updates stored in memory may also strain the RAM a bit, this is why we keep the 4G as the absolutely basic requirement and add upon it depending on the user's configuration.

**ATTENTION: use [RFC2622 operators](https://bgpartemis.readthedocs.io/en/latest/basicconf/#prefixes) wisely, while they are easy to express they may represent billions of prefixes underneath!**

## Screenshots
Please check [UI-how-to-and-screenshots](https://bgpartemis.readthedocs.io/en/latest/uioverview/).

## Issues and Fixes
* IPv4 DNS resolvers

For the RIPE RIS monitors to work, you need to have an IPv4 DNS resolver on the machine that runs the backend docker container.

* Browser support and compatibility

Some older version of browsers do not use session cookies by default on the Fetch API. This means that communication with GraphQL will not work and you will have parseJSON syntax error on the console of the browser.

To fix this, either update your browser or download the newest version of the tool.

* Storage of ARTEMIS on NFS

Due to time-sensitive operations in DB and continuous interaction with the rest of the system, it is strongly discouraged to deploy Artemis on a VM where the VM’s virtual disk resides on an NFS based storage system. NFS has been proved to be a bottleneck when Artemis tries to apply operations in the DB, which results on degradation of performance and numerous false positive alarms.

If deployed in a VM, we encourage you to use local storage for the VM’s HDD. This deployment can guarantee proper processing of the BGP updates on time.
