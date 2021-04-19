In case there is a need to move the `artemis` folder (incl. git code)
to a new location due to e.g., permission issues, the following steps can be followed:

1. Stop any running ARTEMIS instances (use `down`; see also [this section](https://bgpartemis.readthedocs.io/en/latest/running/#stopping-and-exiting-artemis)).
2. Backup your `local_configs` folder; this includes backend, monitor and frontend configuration files.
3. Backup your `postgres-data-current` folder; this includes BGP update and hijack information, as well
   as related statistics, old configurations and intended service states.
   You can delete it altogether if you do not need this kind of state and want to start with a clean DB.
4. Backup your `mongo-data` folder; this includes the user DB used to authenticate and authorize frontend users.
5. Backup your `.env` file; this includes all environment variables used for ARTEMIS (see also [this page](https://bgpartemis.readthedocs.io/en/latest/envvars/)).
6. Backup any `docker-compose` yaml files that you might have changed with custom volume mappings, environment variables, etc.
7. Clone ARTEMIS anew in a new filesystem location: `git clone https://github.com/FORTH-ICS-INSPIRE/artemis`.
8. Run the inverse steps 6, 5, 4, 3 and 2 (restore from backup locations).
9. Start ARTEMIS as usual.

For `kubernetes` setups please consult the ARTEMIS team in Slack.
