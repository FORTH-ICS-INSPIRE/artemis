This is a Proof of Concept (PoC) implementation of an autoconfiguration setup to be used with ARTEMIS.

## Setup architecture

```
 ----------------          -------------          -------------
| ExaBGP Monitor |        | MONITOR AS  |        |  CLIENT AS  |
|    AS65001     |  eBGP  |   AS65003   |  eBGP  |   AS65004   |
|      exa       | ------ | r03 (goBGP) | ------ | r04 (goBGP) |
|    1.1.1.11    |        |   1.1.1.13  |        |  1.1.1.14   |
 ----------------          -------------          -------------
        |
     ARTEMIS
```

## Auto-configuration steps
1. AS65004 announces 1K routes.
2. AS65003 sees them and relays them to the exaBGP monitor for auto-configuration.
3. ARTEMIS writes the configuration file automatically.

## How to run

1. In `docker-compose.yaml`, edit volumes to point to the PoC's files:

    ```
    version: '3'
    services:
      configuration:
        ...
        volumes:
          ...
          - ./poc_autoconf/configs/artemis/:/etc/artemis/
          ...
      ...
      fileobserver:
        ...
        volumes:
          ...
          - ./poc_autoconf/configs/artemis/:/etc/artemis/
          ...
    ```

2. Run the following command and check the ARTEMIS UI:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocautoconf.yaml up -d
   ```

   After it is up and running, activate ARTEMIS exabgp tap.

3. Connect to `r04` and  announce a new prefix:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global rib add 192.168.0.0/16 -a ipv4
   ```

4. Check in the UI that the configuration has been updated. You can repeat this to see a corresponding withdrawal:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global rib del 192.168.0.0/16 -a ipv4
   ```

5. For stress-testing, create 500 routes of the form 192.$i.$j.0/24 and 500 routes of the form 2001:db8:$i:$j::/64 where i in (1 .. 10) and j in (1 .. 100):

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   ./add_routes.sh
   ```

6. Check in the UI that the configuration has been updated. You can repeat this to see all corresponding withdrawals:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r04 sh
   gobgp global del all -a ipv4
   gobgp global del all -a ipv6
   ```
