This is a Proof of Concept (PoC) implementation of an autoconfiguration setup to be used with ARTEMIS.

## Setup architecture

```
 ----------------          -------------          -------------
| ExaBGP Monitor |        | MONITOR AS  |        | EXTERNAL AS |
|    AS65001     |  eBGP  |   AS65003   |  eBGP  |   AS65004   |
|      exa       | ------ | r03 (goBGP) | ------ | r04 (goBGP) |
|    1.1.1.11    |        |   1.1.1.13  |        |  1.1.1.14   |
 ----------------          -------------          -------------
        |
     ARTEMIS
```

## Hijack mitigation steps
1. AS65004 announces 10K routes.
2. AS65003 sees them and relays them to the exaBGP monitor for auto-configuration.
3. ARTEMIS writes the configuration file automatically.

## How to run

1. In `docker-compose.yaml`, edit volumes to point to the PoC's files:

    ```
    version: '3'
    services:
      backend:
        ...
        volumes:
          - ./poc_autoconf/configs/artemis/:/etc/artemis/
          ...
      ...
    ```

2. Run the following command and check the ARTEMIS UI:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocautoconf.yaml up -d
   ```

3. Connect to `r04` and  announce a new prefix:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global rib add 192.168.0.0/16
   ```

4. Check in the UI that the configuration has been updated. You can repeat this to see a corresponding withdrawal:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global rib del 192.168.0.0/16
   ```

5. For stress-testing, create 1000 routes of the form 192.$i.$j.0/24 where i in (1 .. 10) and j in (1 .. 100):

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   ./add_routes.sh
   ```

6. 4. Check in the UI that the configuration has been updated. You can repeat this to see all corresponding withdrawals:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global del all
   ```
