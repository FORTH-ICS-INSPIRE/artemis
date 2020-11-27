Steps:

1. Add `.env` variables
2. Update `artemis-chart` configmaps
3. Update `artemis-chart` deployments
4. Update `artemis-chart` values
5. Add `Dockerfile`
6. Add `LICENSE`
7. Add `Makefile`
8. Add needed config files
9. Add needed code to run in the new container under `core` folder
10. Add new `entrypoint`
11. Add new `requirements.txt`
12. Add `wait-for` script
13. Make any changes necessary in dependent containers that use the new one
14. Append the new container information in `docker-compose`, e.g.,
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
15. Document the new microservice
