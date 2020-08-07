See [this PR](https://github.com/FORTH-ICS-INSPIRE/artemis/pull/213) for a complete example (where we decoupled
monitor from backend). Steps:

1. Add `.env` variables
2. Update `artemis-chart` configmaps
3. Update `artemis-chart` deployments
4. Update `artemis-chart` values
5. Add new supervisor (plus configuration) and update the old one
6. Add `Dockerfile`
7. Add `LICENSE`
8. Add `Makefile`
9. Add needed config files
10. Add `listener` module for supervisor process(es)
11. Add needed code to run in the new container
12. Add new `entrypoint`
13. Add new `requirements.txt`
14. Add `wait-for` script
15. Make any changes necessary in dependent containers that use the new one
16. Append the new container information in `docker-compose`, e.g.,
```
    my_microservice:
        image: ...
        container_name: my_microservice
        restart: always
        depends_on:
            - ...
        networks:
            - artemis
        expose:
            - ${...}
        environment:
            ...: ${...}
        volumes:
            - ...:...
```
