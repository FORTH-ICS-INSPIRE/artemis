#!/bin/bash

if [[ "${DB_BACKUP}" == "true" ]]; then
    cat > /etc/periodic/daily/backup <<EOF
#!/bin/sh
pg_dump -d $POSTGRES_DB -U $POSTGRES_USER -F t -f /backup/db.tar > /backup/db.log 2>&1
EOF
    chmod +x /etc/periodic/daily/backup
else
    [ -e /etc/periodic/daily/backup ] && rm /etc/periodic/daily/backup
fi

re='^[0-9]+$'
if [[ $DB_AUTOCLEAN =~ $re ]]; then
    cat > /etc/periodic/hourly/cleanup <<EOF
#!/bin/sh
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "DELETE FROM bgp_updates WHERE timestamp < NOW() - interval '${DB_AUTOCLEAN} hours' AND hijack_key=ARRAY[]::text[];"
EOF
    chmod +x /etc/periodic/hourly/cleanup
else
    [ -e /etc/periodic/hourly/cleanup ] && rm /etc/periodic/hourly/cleanup
fi

re='^[0-9]+$'
if [[ $DB_HIJACK_DORMANT =~ $re ]]; then
    cat > /etc/periodic/hourly/dormant <<EOF
#!/bin/sh
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "UPDATE hijacks SET dormant=true WHERE time_last < NOW() - interval '${DB_HIJACK_DORMANT} hours' AND active=true AND dormant=false;"
EOF
    chmod +x /etc/periodic/hourly/dormant
else
    [ -e /etc/periodic/hourly/dormant ] && rm /etc/periodic/hourly/dormant
fi

crond && docker-entrypoint.sh postgres
