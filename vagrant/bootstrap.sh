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
git pull origin master

# Setting up ARTEMIS

#echo "[+] Setting up local configuration files..."
mkdir -p local_configs && mkdir -p local_configs/backend && mkdir -p local_configs/monitor && mkdir -p local_configs/frontend
cp -rn backend/configs/* local_configs/backend && cp -rn backend/supervisor.d local_configs/backend && cp -rn monitor/configs/* local_configs/monitor
cp -rn monitor/supervisor.d local_configs/monitor && cp -rn frontend/webapp/configs/* local_configs/frontend
#echo "[+] ARTEMIS VM provisioning completed"

# Setting up firewall

apt-get -y install ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow https
ufw allow ssh
ufw allow in on lo to any
ufw enable

reboot
