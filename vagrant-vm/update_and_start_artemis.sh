#!/bin/bash

echo "Updating and starting ARTEMIS..."
cd /home/vagrant/artemis
if [ -e "vagrant" ]; then
    cp vagrant/vagrant-docker-compose.yaml docker-compose.yaml
fi
git stash
# TODO: replace with master after merge!
git pull origin modularization
git stash pop
docker-compose pull
docker-compose up -d
