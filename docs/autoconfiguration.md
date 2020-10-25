## ExaBGP workflow

The workflow to enable auto-configuration via trusted local feeds (over exaBGP) is the following:

1. First, connect ARTEMIS exabgp container with your local feed, following the steps in [this wiki section](https://github.com/FORTH-ICS-INSPIRE/artemis/wiki#receiving-bgp-feed-from-local-routerroute-reflectorbgp-monitor-via-exabgp).

2. Then, you may start with a minimal configuration file as follows:

        prefixes: {}
        monitors:
          riperis: [''] # by default this uses all available monitors
          bgpstreamlive:
            - routeviews
            - ris
            - caida
          exabgp:
            - ip: exabgp # this will automatically be resolved to the exabgp container's IP
              port: 5000 # default port
              autoconf: "true"
        asns: {}
        rules: []

3. Since you have enabled the `autoconf` flag in exabgp, all BGP updates which are received on the
associated feed and are of the form ("A" meaning announcement):

        Prefix: [..., Origin_ASN] ("A")

    (even with path prepending) will be processed by ARTEMIS as legal advertisements.
    Withdrawals of the prefix will result in its removal from the configuration (together with its associated rules).

    **Important: All announcements on the trusted feed will result in ARTEMIS treating them as
    ground truth; please make sure that you perform the needed filtering before propagating such
    BGP updates to ARTEMIS. For example, if you are using a route collector to send your routes to ARTEMIS (recommended),
    please configure the corresponding session to strip the ASN of the collector,
    in case it is sth different than your origin(s) (eBGP)**.

4. After, e.g., the following sample BGP update reaches ARTEMIS coming from your trusted RC:

        192.168.1.0/24: [..., 1] ("A")

    The configuration will be auto-populated as follows:

        prefixes:
          AUTOCONF_P_192_168_1_0_24: &AUTOCONF_P_192_168_1_0_24
          - 192.168.1.0/24
        monitors:
          riperis: [''] # by default this uses all available monitors
          bgpstreamlive:
          - routeviews
          - ris
          - caida
          exabgp:
          - ip: exabgp   # this will automatically be resolved to the exabgp container's IP
            port: 5000   # default port
            autoconf: "true"
        asns:
          AUTOCONF_AS_1: &AUTOCONF_AS_1
          - 1
        rules:
        - prefixes:
          - *AUTOCONF_P_192_168_1_0_24
          origin_asns:
          - *AUTOCONF_AS_1
          mitigation: manual

5. The aforementioned process does not need any more configuration on your side besides setting up the eBGP session between your RC and ARTEMIS; however it populates rules to cover `*|0|-|*` hijacks.

     If you also want ARTEMIS to cover `*|1|-|*` hijacks, you need to signal it with your neighbor information. To do this, we recommend to set communities in your route maps signaling the asns (e.g., peer groups) to which you propagate the announcements coming from your own network (and not from other peers, customers or upstreams).

     To help you with this, we provide the following route-map configuration example that implements the requested functionality:

        ...
        router bgp 1
            bgp router-id 1.1.1.1

            ! announced networks
            network 192.168.1.0/24 route-map SET-SELF-COMM
            ...
            ! inbound/outbound policy
            ...
            neighbor MONITOR peer-group
            neighbor MONITOR route-map RM-MONITOR-IN in
            neighbor MONITOR route-map RM-MONITOR-OUT out
            neighbor MONITOR next-hop-self

            ! upstream provider
            neighbor 10.0.1.2 remote-as 3
            ...
            neighbor 10.0.1.2 description Primary Transit Provider AS 3
            ...

            ! backup provider
            neighbor 10.0.2.2 remote-as 4
            ...
            neighbor 10.0.2.2 description Backup Transit Provider AS 4
            ...

            ! peer
            ...

            ! customer
            ...

            ! monitors
            neighbor 192.168.10.2 remote-as <MONITOR_AS>
            neighbor 192.168.10.2 peer-group MONITOR
            neighbor 192.168.10.2 ebgp-multihop 2
            neighbor 192.168.10.2 description Local Exabgp RC

        ...

        ! Route map for locally originated networks
        route-map SET-SELF-COMM permit 10
            set community 1:1 additive

        ...

        ! Route map for monitors.
        ! Block all incoming advertisements
        route-map RM-MONITOR-IN deny 10

        ! Here declare also the neighbors
        ! to whom these prefixes are advertised
        route-map RM-MONITOR-OUT permit 10
            match community selforig
            set community 1:3 additive
            on-match next
        route-map RM-MONITOR-OUT permit 20
            match community selforig
            set community 1:4 additive
            on-match next
        route-map RM-MONITOR-OUT permit 30

        ! community list matching self-originated route entries
        ip community-list standard selforig permit 1:1

        ...

    Having configured this in your BGP configuration, the neighbor info is propagated also to ARTEMIS. After, e.g., the following sample BGP update reaches ARTEMIS coming from your trusted RC:

        192.168.1.0/24: [1] ("A"), communities: 1:3 1:4

    The configuration will be auto-populated as follows:

        prefixes:
          AUTOCONF_P_192_168_1_0_24: &AUTOCONF_P_192_168_1_0_24
          - 192.168.1.0/24
        monitors:
          riperis: [''] # by default this uses all available monitors
          bgpstreamlive:
          - routeviews
          - ris
          - caida
          exabgp:
          - ip: exabgp   # this will automatically be resolved to the exabgp container's IP
            port: 5000   # default port
            autoconf: "true"
        asns:
          AUTOCONF_AS_1: &AUTOCONF_AS_1
          - 1
          AUTOCONF_AS_3: &AUTOCONF_AS_3
          - 3
          AUTOCONF_AS_4: &AUTOCONF_AS_4
          - 4
        rules:
        - prefixes:
          - *AUTOCONF_P_192_168_1_0_24
          origin_asns:
          - *AUTOCONF_AS_1
          neighbors:
          - *AUTOCONF_AS_3
          - *AUTOCONF_AS_4
          mitigation: manual

    Note that withdrawals will result in prefix and rule deletion (but ASNs are preserved for future use).

## Notes

1. Only exaBGP monitoring can be current used for auto-configuration.

2. Please use only one source of autoconf ground truth at a time.
