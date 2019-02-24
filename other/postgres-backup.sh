#!/bin/sh
pg_dump -d $POSTGRES_DB -U $POSTGRES_USER -F t -f /tmp/db.tar > /tmp/db.log 2>&1
