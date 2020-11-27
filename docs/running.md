# Running ARTEMIS

## Starting ARTEMIS

You can start ARTEMIS as a multi-container application by running:
```
docker-compose up -d
```
or if you want additional services:
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml -f ... up -d
```
`-d` means running in detached mode (as a daemon; recommended mode).

**RECOMMENDATION: After starting ARTEMIS, always check the logs by running:**
```
docker-compose logs
```
**or**:
```
docker-compose -f ... logs
```
**The addition of a `-f` flag after the logs keyword will provide you running logs.
Checking them is important to see if something went wrong. Consult also [ARTEMIS-logging](https://bgpartemis.readthedocs.io/en/latest/loggingconf/)**.
If everything went ok you will see an output as follows (may differ if you open up the UI in parallel):
```
...
database_1           | process - 2020-11-27 13:01:35,969 - INFO @ run: data worker started
autoignore_1         | process - 2020-11-27 13:01:35,971 - INFO @ run: needed data workers started: ['prefixtree', 'database']
rabbitmq             | 2020-11-27 13:01:35.984 [info] <0.1062.0> accepting AMQP connection <0.1062.0> (172.18.0.9:40106 -> 172.18.0.3:5672)
rabbitmq             | 2020-11-27 13:01:35.987 [info] <0.1065.0> accepting AMQP connection <0.1065.0> (172.18.0.16:51398 -> 172.18.0.3:5672)
rabbitmq             | 2020-11-27 13:01:35.988 [info] <0.1062.0> connection <0.1062.0> (172.18.0.9:40106 -> 172.18.0.3:5672): user 'guest' authenticated and granted access to vhost '/'
rabbitmq             | 2020-11-27 13:01:35.991 [info] <0.1065.0> connection <0.1065.0> (172.18.0.16:51398 -> 172.18.0.3:5672): user 'guest' authenticated and granted access to vhost '/'
autoignore_1         | process - 2020-11-27 13:01:36,004 - INFO @ run: data worker initiated
autoignore_1         | process - 2020-11-27 13:01:36,007 - INFO @ run: data worker started
rabbitmq             | 2020-11-27 13:01:36.018 [info] <0.1099.0> accepting AMQP connection <0.1099.0> (172.18.0.16:51402 -> 172.18.0.3:5672)
rabbitmq             | 2020-11-27 13:01:36.043 [info] <0.1099.0> connection <0.1099.0> (172.18.0.16:51402 -> 172.18.0.3:5672): user 'guest' authenticated and granted access to vhost '/'
```

Extra services that you can use with ARTEMIS are:

* `exabgp`: local exaBGP monitor
* `grafana`: visual interfaces/dashboards; please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/grafanadash/)

## Stopping and exiting ARTEMIS

Note that to gracefully terminate ARTEMIS and all its services you can use the following command:
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml stop
```
If you want to remove the containers as well: (**warning**: whatever file/directory is not properly mapped to a persistent local file/directory will be erased after container tear-down):
```
docker-compose -f docker-compose.yaml -f docker-compose.<extra_service>.yaml down
```
In case you do not use any extra services during composition, you can simply use:
```
docker-compose stop
docker-compose down
```
respectively.

## Per-service CLI controls

You can also access ARTEMIS microservices (if required) via CLI, by executing the following command:
```
docker-compose exec <microservice> bash
```
This will provide you access to the bash entrypoint (assuming it is provided) of the microservice container.

To control microservices separately:
```
docker-compose start|stop|restart <microservice>
```
