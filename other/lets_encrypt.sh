#!/bin/bash
set -e

sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:certbot/certbot
sudo apt-get update
sudo apt install -y python-certbot-nginx

# obtain certs for the domain of the ARTEMIS deployment
sudo certbot --nginx certonly \
     --keep --agree-tos \
     --email <email_address> --no-eff-email \
     --cert-name <domain_name> \
     --domain <domain_name>
