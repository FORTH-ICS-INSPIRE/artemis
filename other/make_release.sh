#!/bin/bash

RELEASE=$(grep "SYSTEM_VERSION=" ../.env | sed "s/SYSTEM_VERSION=//" | tr --delete '\n')

echo "[+] Releasing '$RELEASE'..."

echo "[+] Pulling latest images..."
docker pull inspiregroup/artemis-riperistap:latest
docker pull inspiregroup/artemis-bgpstreamlivetap:latest
docker pull inspiregroup/artemis-bgpstreamkafkatap:latest
docker pull inspiregroup/artemis-bgpstreamhisttap:latest
docker pull inspiregroup/artemis-exabgptap:latest
docker pull inspiregroup/artemis-autoignore:latest
docker pull inspiregroup/artemis-autostarter:latest
docker pull inspiregroup/artemis-configuration:latest
docker pull inspiregroup/artemis-database:latest
docker pull inspiregroup/artemis-detection:latest
docker pull inspiregroup/artemis-fileobserver:latest
docker pull inspiregroup/artemis-mitigation:latest
docker pull inspiregroup/artemis-notifier:latest
docker pull inspiregroup/artemis-prefixtree:latest
docker pull inspiregroup/artemis-tempfrontend:latest

echo "[+] Tagging latest images with '$RELEASE'..."
docker tag inspiregroup/artemis-riperistap:latest inspiregroup/artemis-riperistap:$RELEASE
docker tag inspiregroup/artemis-bgpstreamlivetap:latest inspiregroup/artemis-bgpstreamlivetap:$RELEASE
docker tag inspiregroup/artemis-bgpstreamkafkatap:latest inspiregroup/artemis-bgpstreamkafkatap:$RELEASE
docker tag inspiregroup/artemis-bgpstreamhisttap:latest inspiregroup/artemis-bgpstreamhisttap:$RELEASE
docker tag inspiregroup/artemis-exabgptap:latest inspiregroup/artemis-exabgptap:$RELEASE
docker tag inspiregroup/artemis-autoignore:latest inspiregroup/artemis-autoignore:$RELEASE
docker tag inspiregroup/artemis-autostarter:latest inspiregroup/artemis-autostarter:$RELEASE
docker tag inspiregroup/artemis-configuration:latest inspiregroup/artemis-configuration:$RELEASE
docker tag inspiregroup/artemis-database:latest inspiregroup/artemis-database:$RELEASE
docker tag inspiregroup/artemis-detection:latest inspiregroup/artemis-detection:$RELEASE
docker tag inspiregroup/artemis-fileobserver:latest inspiregroup/artemis-fileobserver:$RELEASE
docker tag inspiregroup/artemis-mitigation:latest inspiregroup/artemis-mitigation:$RELEASE
docker tag inspiregroup/artemis-notifier:latest inspiregroup/artemis-notifier:$RELEASE
docker tag inspiregroup/artemis-prefixtree:latest inspiregroup/artemis-prefixtree:$RELEASE
docker tag inspiregroup/artemis-tempfrontend:latest inspiregroup/artemis-tempfrontend:$RELEASE

echo "[+] Pushing '$RELEASE' images to docker cloud..."
docker push inspiregroup/artemis-riperistap:$RELEASE
docker push inspiregroup/artemis-bgpstreamlivetap:$RELEASE
docker push inspiregroup/artemis-bgpstreamkafkatap:$RELEASE
docker push inspiregroup/artemis-bgpstreamhisttap:$RELEASE
docker push inspiregroup/artemis-exabgptap:$RELEASE
docker push inspiregroup/artemis-autoignore:$RELEASE
docker push inspiregroup/artemis-autostarter:$RELEASE
docker push inspiregroup/artemis-configuration:$RELEASE
docker push inspiregroup/artemis-detection:$RELEASE
docker push inspiregroup/artemis-fileobserver:$RELEASE
docker push inspiregroup/artemis-mitigation:$RELEASE
docker push inspiregroup/artemis-notifier:$RELEASE
docker push inspiregroup/artemis-prefixtree:$RELEASE
docker push inspiregroup/artemis-tempfrontend:$RELEASE
