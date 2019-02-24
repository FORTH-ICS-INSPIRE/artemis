#!/bin/bash

if [[ "${DB_BACKUP}" == "true" ]]; then
    cat > /etc/periodic/daily/backup <<EOF
#!/bin/sh
pg_dump -d $POSTGRES_DB -U $POSTGRES_USER -F t -f /tmp/db.tar > /tmp/db.log 2>&1
EOF
fi

re='^[0-9]+$'
if [[ $DB_AUTOCLEAN =~ $re ]]; then
    cat > /etc/periodic/hourly/cleanup <<EOF
#!/bin/sh
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "DELETE FROM bgp_updates WHERE timestamp < NOW() - interval '${DB_AUTOCLEAN} hours' AND hijack_key=ARRAY[]::text[];"
EOF
fi

crond && docker-entrypoint.sh postgres
