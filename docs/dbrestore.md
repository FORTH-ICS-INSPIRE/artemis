In case you encounter any issues please contact the ARTEMIS team. Feel free to edit this page accordingly.

ATTENTION: First, check that [this file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/other/db/data/restore.sql) has the correct credentials, db name and db.tar location. Volume mappings exist already in the [docker-compose file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.yaml#L123) (for backup and current data, as well as db configuration and scripts).

Then, follow the next steps:
1. shutdown ARTEMIS
   ```
   docker-compose down
   ```
2. If you already have root access, just do the following command and proceed to step 5:
   ```
   rm -rf postgres-data-current/*
   ```
   otherwise start backend container to use for cleaning the current data (docker has root access already), and proceed:
   ```
   docker run --rm -ti --entrypoint="bash" -v "$(pwd)/postgres-data-current:/tmp/data"  inspiregroup/artemis-backend
   ```
3. delete postgres-data folders from within the container
   ```
   root@4b9830aa0fff:~# rm -rf /tmp/data/*
   ```
4. exit the container
   ```
   root@4b9830aa0fff:~# exit
   ```
5. initiate postgres container
   ```
   docker-compose run postgres
   ```
   Now the postgres container is running. Leave the current terminal open.
6. from a new terminal, attach to running postgres container. To first see the name of the container, do:
   ```
   $ docker-compose ps
         Name                       Command              State    Ports
   -------------------------------------------------------------------------
   artemis_postgres_run_{container_id}   docker-entrypoint.sh postgres   Up      5432/tcp
   ```
   and then attach:
   ```
   docker exec -ti artemis_postgres_run_{container_id} bash
   ```
7. perform the restoration:
   ```
   bash-4.4# psql -U artemis_user -d artemis_db < docker-entrypoint-initdb.d/data/restore.sql
   ```
   Ignore the presented errors, since they do not affect the correctness of the db. You should see something like the following:
   ```
   WARNING: errors ignored on restore: ...
   You are now connected to database "artemis_db" as user "artemis_user".
   ALTER DATABASE
   bash-4.4#
   ```
8. exit the postgres container:
   ```
   bash-4.4# exit
   ```
9. stop and remove postgres container:
   ```
   docker stop artemis_postgres_run_{container_id}
   docker rm artemis_postgres_run_{container_id}
   ```
10. make sure everything is clean
    ```
    docker-compose down
    ```
11. start ARTEMIS normally
    ```
    docker-compose -f ... up -d
    ```
