#!/bin/sh
psql -d $POSTGRES_DB -U $POSTGRES_USER -c "DELETE FROM bgp_updates WHERE timestamp < NOW() - interval '1 hours' AND handled=true AND hijack_key=ARRAY[]::text[];"
