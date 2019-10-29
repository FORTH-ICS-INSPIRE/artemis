#!/bin/sh
docker cp backend:/root/core/.coverage .coverage
sed -i "s;/root/core/;./backend/core/;g" .coverage
coverage xml
