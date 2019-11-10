ALTER DATABASE artemis_db SET timescaledb.restoring='on';
-- execute the restore (or from a shell)
\! pg_restore -Ft -U artemis_user -d artemis_db /tmp/db.tar
-- connect to the restored db
\c artemis_db
ALTER DATABASE artemis_db SET timescaledb.restoring='off';
