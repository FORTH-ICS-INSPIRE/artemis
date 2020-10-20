This is a Proof of Concept (PoC) implementation of a mitigation setup to be used with ARTEMIS.

We include a script that receives the information of the hijack (id + prefix), and upon
execution advertises the two subnets of the prefix performing deaggregation.

## Setup architecture

```
 ----------------          -------------          -------------
| ExaBGP Monitor |        | MONITOR AS  |        | EXTERNAL AS |
|    AS65001     |  eBGP  |   AS65003   |  eBGP  |   AS65004   |
|      exa       | ------ | r03 (goBGP) | ------ | r04 (goBGP) |
|    1.1.1.11    |        |   1.1.1.13  |        |  1.1.1.14   |
 ----------------          -------------          -------------
        |                                  eBGP        | | eBGP
     ARTEMIS                     ----------------------- |
        |                        |                       |
 --------------          --------------          --------------
| ExaBGP Deagg |        |    PEER AS   |        |  HIJACKER AS |
|    AS65002   |  eBGP  |    AS65005   |  eBGP  |    AS65006   |
|      exa     | ------ |  r05 (goBGP) | ------ |  r06 (goBGP) |
|    1.1.1.12  |        |    1.1.1.15  |        |    1.1.1.16  |
 --------------          --------------          --------------
```

## Hijack mitigation steps
1. AS65002 announces prefix 192.168.0.0/16 legally.
2. The hijacker AS (AS65006) announces prefix 192.168.0.0/16 whose legal origin is AS65002.
3. ARTEMIS detects the hijack using its feed from AS65003 via the ExaBGP monitor.
4. ARTEMIS mitigates the hijack (by order of the user) by deaggregating the hijacked prefix and announcing the new
BGP updates via PEER AS AS65005.

## How to run

1. In `docker-compose.yaml`, edit volumes to point to the PoC's files:

    ```
    version: '3'
    services:
      backend:
        ...
        volumes:
          - ./poc_mitigate_deaggregate/configs/artemis/:/etc/artemis/
          - ./poc_mitigate_deaggregate/poc_mitigate_deaggregate.py:/root/poc_mitigate_deaggregate.py
          ...
      ...
    ```

2. Run the following command and check the ARTEMIS UI:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml up -d
   ```
3. Connect to `r06` and  announce the hijacked prefix:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml exec r06 sh
   gobgp global rib add 192.168.0.0/16
   ```
4. Observe the hijack in ARTEMIS and initiate the mitigation action.
