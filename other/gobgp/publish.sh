#!/bin/sh

docker-compose exec r02 gobgp global rib add 11.0.1.0/24
docker-compose exec r02 gobgp global rib add 11.0.2.0/24
docker-compose exec r02 gobgp global rib add 11.0.3.0/24
