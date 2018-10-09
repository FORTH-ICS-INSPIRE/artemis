#!/bin/sh
pg_dump -d artemis_db -U artemis_user -a -F t -f /tmp/db.tar &> /tmp/db.log
