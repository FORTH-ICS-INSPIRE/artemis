## Scaling microservices

You can instruct the tool to run multiple instances of any of the following microservices.

* `autoignore`

* `autostarter`

* `configuration`

* `database`

* `detection`

* `fileobserver`

* `mitigation`

* `notifier`

* `prefixtree`

* `riperistap`

* `bgpstreamlivetap`

* `bgpstreamkafkatap`

* `bgpstreamhisttap`

* `exabgptap`

However, we recommend not scaling tap microservices,
and in case you have issues with large BGP update loads, to scale only
the following microservices:

* `detection` (for load-balancing detection processes)

* `prefixtree` (for load-balancing prefix tree lookups; attention, this requires memory!)

* `database` (for load-balancing database access)

To apply scaling (can be upwards or downwards):

* Before you initiate artemis:

  ```
  docker-compose up --scale <service_1>=number_of_service_1_replicas> --scale <service_2>=number_of_service_2_replicas> ... -d
  ```

* While ARTEMIS is running (live):

  ```
  docker-compose scale <service_1>=number_of_service_1_replicas>
  docker-compose scale <service_2>=number_of_service_2_replicas>
  ...
  ```
