apt-get install ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow from <GW_VM_IP> to any port 22 proto tcp
ufw allow from 139.91.0.0/16 to any port 443 proto tcp
ufw allow from <CAIDA_PREFIX> to any port 443 proto tcp
ufw allow from <TESTER_PREFIX> to any port 443 proto tcp
ufw allow in on lo to any
ufw enable
