#!/bin/bash

function upgrade() {
  echo "[+] Deleting all containers" && \
  docker-compose down && \
  echo "[+] Deleting current database" && \
  rm -rf postgres-data-current && \
  echo "[+] Pulling new versions for images" && \
  docker-compose pull && \
  echo "[+] Starting database" && \
  docker-compose up -d postgres && \
  sleep 15 && \
  echo "[+] Restoring previous database" && \
  docker-compose exec postgres sh -c 'psql -U artemis_user -d artemis_db < docker-entrypoint-initdb.d/data/restore.sql' && \
  echo "[+] Cleaning up" && \
  docker-compose down
  echo "[+] Upgraded to latest version.. Run docker-compose up to start"
}

# Checks
if [[ -d postgres-data-current && ! -r postgres-data-current ]]; then
  echo "[!] You don't have permission to delete current database. Run sudo chmod -R 777 postgres-data-*"
  exit -1
fi
current_version=$(cat .env | grep -Ei "SYSTEM_VERSION=(.*)" | cut -d= -f2)
if [ "$current_version" != "latest" ]; then
  echo "[!] This script only works when SYSTEM_VERSION is set to latest"
  exit -1
fi

out=$(docker-compose ps -q)
if [ -z "$out" ]; then
  echo "[!] Setup is already stopped.. this means we are going to use the daily backup and not the latest"
  read -p "[?] Continue (y/[n])? " -n 1 -r
  echo # (optional) move to a new line
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    upgrade
  else
    exit -1
  fi
else
  docker-compose exec postgres sh -c 'pg_dump -d $POSTGRES_DB -U $POSTGRES_USER -F t -f /tmp/db.tar > /tmp/db.log 2>&1' && \
  upgrade
fi
