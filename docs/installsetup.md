# ARTEMIS Installation and Setup

## Install Packages

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
   git clone https://github.com/FORTH-ICS-INSPIRE/artemis
   ```

6. The docker-compose utility is configured to pull the latest **stable** released images that are built remotely on [docker cloud](https://cloud.docker.com/). Run the following:
    ```
    cd artemis
    docker-compose pull
    ```
    to trigger this.

    No further installation/building actions are required on your side at this point.

## Rootless Docker

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

## Setup Tool

1. Edit environment variables in `.env` file (especially the security-related variables); please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/envvars/) for more information on the env variables.

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
   ARTEMIS_WEB_HOST=artemis.com # please adjust to your local server domain
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
   cp -rn backend-services/configs/* local_configs/backend && \
   cp backend-services/configs/redis.conf local_configs/backend/redis.conf && \
   cp -rn monitor-services/configs/* local_configs/monitor && \
   cp -rn frontend/webapp/configs/* local_configs/frontend
   ```
   The source mappings in `docker-compose.yaml` are already updated by default.
   The `local_configs` directory is NOT under version control.
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
   │   ├── autoconf-config.yaml
   │   ├── config.yaml
   │   ├── logging.yaml
   │   └── redis.conf
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
       └── logging.yaml
   ```

4. Setup `https`: the ARTEMIS web application supports `https` by default to ensure secure access to the application. We use a nginx reverse proxy to terminate SSL connections before forwarding the requests to Flask. To configure your own (e.g., self-signed) certificates, please place in the following folder:
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

## Optional configurations

Optionally, you may edit the file:
```
local_configs/frontend/webapp.cfg
```
to circumvent other default parameters used in the frontend.
These parameters and their explanation can be found at [Additional frontend env variables](https://bgpartemis.readthedocs.io/en/latest/frontendconf/).

Also optionally, you can enable daily backups by changing the `DB_BACKUP` environment variable inside `.env` to true:
```
DB_BACKUP=true
```
The DB will then be regularly backed up (daily) in folder postgres-data-backup.

In order to restore a backed up DB: Please check [Restoring DB from backup](https://bgpartemis.readthedocs.io/en/latest/dbrestore/).

Furthermore, you can decide if you want to delete all old unwanted (non-hijack) BGP updates
by setting the `DB_AUTOCLEAN` environment variable; this marks a time window (in hours)
in which ARTEMIS keeps benign BGP updates. E.g.,
```
DB_AUTOCLEAN=24
```
means that any non-hijack updates older than 24 hours will be deleted by the system.
The default value is false (no deletion).
