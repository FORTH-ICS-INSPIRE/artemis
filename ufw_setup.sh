apt-get install ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow from <GW_VM_IP> to any port 22 proto tcp
ufw allow from <ACCESS_PREFIX_1> to any port 443 proto tcp
ufw allow from <ACCESS_PREFIX_N> to any port 443 proto tcp
ufw allow from <ROUTER_1> to any port 179 proto tcp
ufw allow from <ROUTER_N> to any port 179 proto tcp
ufw allow in on lo to any
ufw enable
