-- some setting to make the output less verbose
\set QUIET on
\set ON_ERROR_STOP on
set client_min_messages to warning;

-- load some variables from the env
\setenv base_dir :DIR
\set base_dir `if [ $base_dir != ":"DIR ]; then echo $base_dir; else echo "/docker-entrypoint-initdb.d"; fi`


\echo # Loading database definition
begin;

\echo # Loading dependencies
-- functions for sending messages to RabbitMQ entities
\ir libs/rabbitmq/schema.sql

\echo # Loading application definitions
\ir data/tables.sql

\echo # Load some default values
\ir data/data.sql

commit;
\echo # ==========================================
