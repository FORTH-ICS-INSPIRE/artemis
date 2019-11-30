#!/bin/bash

RELEASE=$(grep "SYSTEM_VERSION=" ../.env | sed "s/SYSTEM_VERSION=//" | tr --delete '\n')

echo "[+] Releasing '$RELEASE'..."

echo "[+] Pulling latest images..."
docker pull inspiregroup/artemis-backend:latest
docker pull inspiregroup/artemis-frontend:latest
docker pull inspiregroup/artemis-monitor:latest

echo "[+] Tagging latest images with '$RELEASE'..."
docker tag inspiregroup/artemis-backend:latest inspiregroup/artemis-backend:$RELEASE
docker tag inspiregroup/artemis-frontend:latest inspiregroup/artemis-frontend:$RELEASE
docker tag inspiregroup/artemis-monitor:latest inspiregroup/artemis-monitor:$RELEASE

echo "[+] Pushing '$RELEASE' images to docker cloud..."
docker push inspiregroup/artemis-backend:$RELEASE
docker push inspiregroup/artemis-frontend:$RELEASE
docker push inspiregroup/artemis-monitor:$RELEASE
