#!/bin/bash

# Print commands and exit on errors
set -xe

# Installing ARTEMIS packages

#echo "[+] Updating sources..."
apt-get update
#echo "[+] Removing stale docker installations..."
apt-get remove docker docker-engine docker.io containerd runc
#echo "[+] Updating sources..."
apt-get update
#echo "[+] Installing Docker dependencies..."
apt-get install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common
#echo "[+] Adding docker's official GPG key..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
#echo "[+] Adding docker's stable repository..."
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
#echo "[+] Updating sources..."
apt-get update
#echo "[+] Installing latest version of docker engine..."
apt-get install -y docker-ce docker-ce-cli containerd.io
docker -v
#echo "[+] Installed docker version $(docker -v)"
#echo "[+] Downloading latest docker-compose..."
curl -L "https://github.com/docker/compose/releases/download/1.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
#echo "[+] Making docker-compose executable..."
chmod +x /usr/local/bin/docker-compose
#echo "[+] Creating symbolic link for docker-compose..."
ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
docker-compose -v
#echo "[+] Installed docker-compose version $(docker-compose -v)"
#echo "[+] Adding default artemis_user to docker group..."
usermod -aG docker vagrant
#echo "[+] Installing ntp..."
apt-get install -y ntp
#echo "[+] Installing git..."
apt-get install -y git
#echo "[+] Cloning latest ARTEMIS from GitHub..."
git clone https://github.com/FORTH-ICS-INSPIRE/artemis.git
cd artemis
# TODO: replace with master after merge!
git checkout modularization
git pull origin modularization

# Setting up ARTEMIS

#echo "[+] Setting up local configuration files..."
ROOT_ARTEMIS_DIR="."
LOCAL_CONFIGS="$ROOT_ARTEMIS_DIR/local_configs"
LOCAL_CONFIGS_BK="$ROOT_ARTEMIS_DIR/local_configs.bk$(date '+%s')"
[ -d $LOCAL_CONFIGS ] && mkdir -p $LOCAL_CONFIGS_BK && cp -r $LOCAL_CONFIGS $LOCAL_CONFIGS_BK;
mkdir -p $LOCAL_CONFIGS;
mkdir -p $LOCAL_CONFIGS/backend-services;
mkdir -p $LOCAL_CONFIGS/backend-services/autostarter;
mkdir -p $LOCAL_CONFIGS/backend-services/configuration;
mkdir -p $LOCAL_CONFIGS/backend-services/database;
mkdir -p $LOCAL_CONFIGS/backend-services/detection;
mkdir -p $LOCAL_CONFIGS/backend-services/fileobserver;
mkdir -p $LOCAL_CONFIGS/backend-services/mitigation;
mkdir -p $LOCAL_CONFIGS/backend-services/notifier;
mkdir -p $LOCAL_CONFIGS/backend-services/prefixtree;
mkdir -p $LOCAL_CONFIGS/backend-services/redis;
mkdir -p $LOCAL_CONFIGS/monitor-services/riperistap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap;
mkdir -p $LOCAL_CONFIGS/monitor-services/exabgptap;
mkdir -p $LOCAL_CONFIGS/frontend;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/config.yaml ] && cp -n $LOCAL_CONFIGS/backend/config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/autoconf-config.yaml ] && cp -n $LOCAL_CONFIGS/backend/autoconf-config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/autoconf-config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/autostarter/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/autostarter/configs/logging.yaml $LOCAL_CONFIGS/backend-services/autostarter/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/logging.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/database/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/database/configs/logging.yaml $LOCAL_CONFIGS/backend-services/database/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/detection/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/detection/configs/logging.yaml $LOCAL_CONFIGS/backend-services/detection/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/fileobserver/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/fileobserver/configs/logging.yaml $LOCAL_CONFIGS/backend-services/fileobserver/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/mitigation/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/mitigation/configs/logging.yaml $LOCAL_CONFIGS/backend-services/mitigation/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/notifier/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/notifier/configs/logging.yaml $LOCAL_CONFIGS/backend-services/notifier/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/prefixtree/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/prefixtree/configs/logging.yaml $LOCAL_CONFIGS/backend-services/prefixtree/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/redis/configs/redis.conf $LOCAL_CONFIGS/backend-services/redis/redis.conf;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/riperistap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/riperistap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/riperistap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamlivetap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamkafkatap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamhisttap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap/;
[ -d $LOCAL_CONFIGS/monitor ] && cp -rn $LOCAL_CONFIGS/monitor/* $LOCAL_CONFIGS/monitor-services/exabgptap/;
cp -rn $ROOT_ARTEMIS_DIR/monitor-services/exabgptap/configs/* $LOCAL_CONFIGS/monitor-services/exabgptap/;
[ -d $LOCAL_CONFIGS/monitor-services/exabgptap/supervisor.d ] && rm -r $LOCAL_CONFIGS/monitor-services/exabgptap/supervisor.d;
[ -d $LOCAL_CONFIGS/backend ] && rm -r $LOCAL_CONFIGS/backend;
[ -d $LOCAL_CONFIGS/monitor ] && rm -r $LOCAL_CONFIGS/monitor;
cp -rn $ROOT_ARTEMIS_DIR/frontend/webapp/configs/* $LOCAL_CONFIGS/frontend
#echo "[+] ARTEMIS VM provisioning completed"

# Setting up firewall

apt-get -y install ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow https
ufw allow ssh
ufw allow in on lo to any
yes | ufw enable
