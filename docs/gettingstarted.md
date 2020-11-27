# Getting Started

ARTEMIS is built as a multi-container Docker application.
The following instructions will get you a containerized
copy of the ARTEMIS tool up and running on your local machine using the `docker-compose` utility.
For instructions on how to set up ARTEMIS
in a Kubernetes environment, please check the related [docs page](https://bgpartemis.readthedocs.io/en/latest/kubernetes/).

## How to Install and Setup

To download and install the required software packages, please follow steps 1 through 6 described in [this docs section](https://bgpartemis.readthedocs.io/en/latest/installsetup/#install-packages).

To setup the tool (as well as https access to it via the web application), please follow steps 1 through 5 described in [this docs section](https://bgpartemis.readthedocs.io/en/latest/installsetup/#setup-tool).

*Note that specifically for testing purposes, we now support `vagrant` and `VirtualBox` VM automation; please check out [this docs page](https://bgpartemis.readthedocs.io/en/latest/vagrant/) for simple instructions on how to spin up a fully functioning ARTEMIS VM, running all needed microservices, within a minute.*

## How to Run and Configure

1. Start ARTEMIS:

   ```
   docker-compose up -d
   ```

   *Please consult [this docs section](https://bgpartemis.readthedocs.io/en/latest/running/#starting-artemis) if you need to activate additional services.*

2. Visit web UI and configure ARTEMIS:

   ```
   https://<ARTEMIS_HOST>
   ```

   By visiting the system page:

   ```
   https://<ARTEMIS_HOST>/admin/system
   ```

   you can:

   1. edit the basic configuration file of ARTEMIS that serves as the ground truth for detecting BGP hijacks (consult [this docs section](https://bgpartemis.readthedocs.io/en/latest/basicconf/) first)
   2. control the monitoring, detection and mitigation microservices.

3. Stop ARTEMIS (optional)

   ```
   docker-compose stop
   ```

**Note: We highly recommend going through the detailed docs instructions before using ARTEMIS for the first time.** You can further use several other microservices orthogonal to ARTEMIS (like `grafana` and `routinator`) by using the main ARTEMIS `docker-compose` yaml plus the additional yamls:

```
docker-compose -f docker-compose.yaml -f docker-compose.<other_service>.yaml -... <up>/<down>/...
```

## Demo

A running demo of ARTEMIS based on the configuration of our home institute (FORTH) can be found [here](https://demo.bgpartemis.org).

You can access the demo as a guest (non-admin) user by using the following credentials:

```
username: "guest"
password: "guest@artemis"
```

*Please do not request new accounts on the demo portal. Use the given credentials to browse ARTEMIS as a guest user. In case you need admin access, simply clone ARTEMIS locally and use the given configuration file.*
