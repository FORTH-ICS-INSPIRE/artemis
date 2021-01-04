# Upgrading ARTEMIS to a new version

### Main steps

Before upgrading, we recommend that you ensure that there is a recent (at most a day old) backup `db.tar` of the database under `postgres-data-backup`.
Then, do the following:

1. Make sure you have copied the default configs directories under `local_configs`
and have updated the source volume mappings accordingly;
check [this file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml) carefully for
`local_configs` mappings. A sample folder structure for `local_configs` is the following:

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

6. (**Only if migrating to 2.0.0**)

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

   The `-n` flag will prevent overwriting any local changes you have already made.

7. Re-apply local changes (if auto-merge fails, resolve any conflicts)

   ```
   git stash pop
   ```

   **NOTE: when migrating to 2.0.0, the `docker-compose.yaml` file will undergo significant changes
   which you should accept from upstream! If needed, recheck the yaml file and make sure that the correct
   `local-configs` volume mappings are applied.**

8. **Make sure that you also do a**
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
build: ./backend-services/<microservice>
build: ./monitor-services/<microservice>
build: ./frontend
```
Note also that you need to always map your volumes properly (e.g., `./backend-services/<microservice>:/root/....`, etc.).
Custom building can be triggered with:
```
docker-compose -f ... build
```
*Note that for the frontend, you need to make sure that the js-compiled files are
properly generated. You may need to copy them from a pre-built frontend container
to be user. More details to follow (this refers only to custom builds that
require changes to the frontend).*

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
