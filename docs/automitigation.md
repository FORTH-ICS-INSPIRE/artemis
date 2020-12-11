We include a Proof of Concept (PoC) implementation of a mitigation setup to be used with ARTEMIS.

The folder with the needed scripts and configurations is [here](https://github.com/FORTH-ICS-INSPIRE/artemis/tree/master/poc_mitigate_deaggregate).

We include a script that receives the information of the hijack (id + prefix), and upon
execution advertises the two subnets of the prefix, performing deaggregation.

## PoC Setup architecture

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
4. ARTEMIS mitigates the hijack (by order of the user - mitigation action) by deaggregating the hijacked prefix and announcing the new
BGP updates via PEER AS AS65005.

## How to run PoC

1. In `docker-compose.yaml`, edit volumes to point to the PoC's files:

    ```
    version: '3'
    services:
      ...
      configuration:
        ...
        volumes:
          ...
          - ./poc_mitigate_deaggregate/configs/artemis/:/etc/artemis/
          - ./poc_mitigate_deaggregate/poc_mitigate_deaggregate.py:/root/poc_mitigate_deaggregate.py
          ...
      ...
      fileobserver:
        ...
        volumes:
          ...
          - ./poc_mitigate_deaggregate/configs/artemis/:/etc/artemis/
          ...
      mitigation:
        ...
        volumes:
          ...
          - ./poc_mitigate_deaggregate/poc_mitigate_deaggregate.py:/root/poc_mitigate_deaggregate.py
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
4. Observe the hijack in ARTEMIS and initiate the mitigation action. You can optionally invoke the `un-mitigate` action to stop mitigation (not implemented in-PoC-script).

## How to run in production (to be tested)

In case you want to run this in production you can adjust [`poc_mitigate_deaggregate.py`](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/poc_mitigate_deaggregate/poc_mitigate_deaggregate.py) and [`docker-compose.pocmitigatedeaggregate.yaml`](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.pocmitigatedeaggregate.yaml) as needed. So the following steps would be required:

1. Adjust [`poc_mitigate_deaggregate.py`](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/poc_mitigate_deaggregate/poc_mitigate_deaggregate.py) so that it applies what you want it to apply.

2. In `docker-compose.yaml`, edit volumes to point to the mitigation file:

    ```
    version: '3'
    services:
      ...
      configuration:
        ...
        volumes:
          ...
          - ./poc_mitigate_deaggregate/poc_mitigate_deaggregate.py:/root/poc_mitigate_deaggregate.py
          ...
      ...
      mitigation:
        ...
        volumes:
          ...
          - ./poc_mitigate_deaggregate/poc_mitigate_deaggregate.py:/root/poc_mitigate_deaggregate.py
          ...
    ```

3. Edit the [exabgp configuration files](https://github.com/FORTH-ICS-INSPIRE/artemis/tree/master/poc_mitigate_deaggregate/configs/exabgp) according to your router setup. Note that the `monitor` is passive (receiving updates from routers), while the `routecommander` active (sending updates to routers).

4. Adjust [`docker-compose.pocmitigatedeaggregate.yaml`](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.pocmitigatedeaggregate.yaml) so that it maps to your setup (networking, keeping only the exabgp containers, etc.).

5. Initiate ARTEMIS with the new microservices:

   ```
   docker-compose -f docker-compose.yaml -f docker-compose.pocmitigatedeaggregate.yaml up -d
   ```

6. Edit your ARTEMIS configuration file at will:

   ```
   rules:
   - prefixes:
     ...
     origin_asns:
     ...
     neighbors:
     ...
     mitigation:
     "/root/poc_mitigate_deaggregate.py"
   ```

## Notes

Feedback is more than welcome, feel free to expand this section!
