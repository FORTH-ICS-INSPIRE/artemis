#!/bin/bash

artemis_host=$(ip address show enp0s8 | grep 'inet ' | sed -e 's/^.*inet //' -e 's/\/.*$//' | tr -d '\n' 2>/dev/null)
echo "Visit ARTEMIS at: https://${artemis_host} (access: admin@admin.com/Adm!n1234)"
