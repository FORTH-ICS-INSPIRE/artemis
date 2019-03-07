#!/bin/bash
if [[ -f .env && -f docker-compose.yaml ]]; then
    env $(grep -v '#' .env) kompose convert --controller deployment --volumes hostPath -f docker-compose.yaml -o k8s.yaml
    cwd=$(pwd)
    sed -i "/path:.*nginx.conf/a \            type: File" k8s.yaml
    sed -i "/path:.*enabled-plugins/a \            type: File" k8s.yaml
    sed -i "s/enabled-plugins/enabled_plugins/g" k8s.yaml
    sed -i "/path:.*postgres-entrypoint.sh/a \            type: File" k8s.yaml
    sed -i "/path:.*init.sql/a \            type: File" k8s.yaml
    sed -i "/path:.*wait-for/a \            type: File" k8s.yaml
    sed -i "s;$cwd$cwd;$cwd;g" k8s.yaml
else
    echo "Please run the script from root folder"
fi;
