# Local feeds via ExaBGP

### Configuration

Change the following source mapping from [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docker-compose.exabgp.yaml#L11) to:
```
- ./local_configs/monitor/exabgp.conf:/home/config/exabgp.conf
```
Edit the local_configs/monitor-services/exabgptap/exabgp.conf file as follows:
```
group r1 {
    router-id <PUBLIC_IP>; # the public IP of your ARTEMIS host

    process message-logger {
        encoder json;
        receive {
            parsed;
            update;
            neighbor-changes;
        }
        run /usr/lib/python2.7.14/bin/python /home/server.py;
    }

    neighbor <NEIGHBOR_IP> { # the IP of your BGP router/etc.
        local-address <LOCAL_LAN_IP>; # the local LAN IP of your ARTEMIS host
        local-as <LOCAL_ASN>; # the local (private) exaBGP monitor ASN that you will use for peering
        peer-as <PEER_ASN>; # your ASN from which the exaBGP monitor will receive the feed
    }
}
```
Stop the current ARTEMIS instance:
```
docker-compose stop
```
Start ARTEMIS with ExaBGP enabled:
```
docker-compose -f docker-compose.yaml -f docker-compose.exabgp.yaml up -d
```
Login to the UI and configure the monitor using the web application form in
```
https://<ARTEMIS_HOST>/admin/system
```
by setting its IP address and port. An example is the following:
```
...
monitors:
  ...
  exabgp:
    - ip: exabgp # this will automatically be resolved to the exabgp container's IP
      port: 5000 # default port
...
```
### Notes

1. We strongly recommend the use of eBGP instead of iBGP sessions between the
exaBGP monitor and the local router(s), in order to have information that can be better
used by the detection system.

2. Since the exaBGP container is one layer behind the networking
stack of the ARTEMIS host, establishing a successful eBGP connection between your router and
exaBGP will require properly setting the ebgp-multihop attribute on your router, e.g.,**

   ```
   >router bgp <my_as>
   >neighbor <exabgp_public_ip> ebgp-multihop 2 # if the router is one physical hop away
   ```

3. For all options on how to properly configure exaBGP, please visit [this page](https://manpages.debian.org/testing/exabgp/exabgp.conf.5.en.html).
Some useful options are the following:

   ```
   # within the neighbor section to set up md5 passwords
   md5-password <md5-secret>;

   # within the neighbor section to set up both v4 and  v6 advertisements
   family {
        ipv4 unicast;
        ipv6 unicast;
   }

   # the following section goes before the neighbor section to add a route refresh capability
   # needed to retrieve all prefixes from neighbor routers on monitor startup
   capability {
       route-refresh enable;
   }
   ```
