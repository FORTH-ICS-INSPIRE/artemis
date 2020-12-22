## Overview
The ARTEMIS configuration file (config.yaml) is written in YAML (for an ultra-fast intro to its syntax, please check [here](https://learn.getgrav.org/advanced/yaml)). It is contained by default under:

    backend-services/configs

but you should copy the default file to the `local_configs/backend` location.
Detailed instructions on the exact steps can be found [here](https://bgpartemis.readthedocs.io/en/latest/installsetup/#setup-tool).
The local location of your file should eventually be:

    local_configs/backend/config.yaml

The file is composed of 4 sections (Prefixes, Monitors, ASNs, and Rules) described next in detail.
*Reserved words are marked in bold (configuration keywords).*

## Prefixes
This section contains all declared ARTEMIS prefixes. Note that even if a prefix is declared here, it does not mean
it will be monitored by ARTEMIS; only prefixes that are involved with at least one rule (see later section)
are actually monitored and checked for hijacks.

You can create prefix references by prefixing them with "&", which you can later access using the "*" prefix
You can reference both single prefixes as well as lists of prefixes. Both IPv4 and IPv6 are supported.
Be careful to properly reference prefixes that you use in the rules later.

Example:

    prefixes:
        # A reference for a single prefix
        simple_prefix: &my_prefix
            IPv4|IPv6_prefix
        # A reference for a list of prefixes
        simple_prefix_list: &my_prefixes
            - IPv4|IPv6_prefix_1
            - ...
            - IPv4|IPv6_prefix_N

Note that from release 1.1.1 onwards, you can use prefix aggregation operators, as defined in [RFC2622](https://tools.ietf.org/html/rfc2622), to minimize the number of prefixes you have to define in the configuration.
Currently the following operators are supported.

**ATTENTION: use these operators with caution; e.g., a /8^- IPv4 prefix contains 1+ 2 + ... + 2^(32-8)=2^(32-8+1)-1=2^25-->32 million prefixes; a /32^64 IPv6 contains 2^(64-32)=2^32=4 billion prefixes!**

You can optionally include the super-prefix in the configuration prefixes (before or after the operator-suffixed prefixes), so that ARTEMIS can smartly monitor the super-prefix and its sub-prefixes instead of every single sub-prefix individually:

* ^- is the exclusive more specifics operator; it stands for the more specifics of the address prefix excluding the address prefix itself.  For example, 128.9.0.0/16^- contains all the more specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
* ^+ is the inclusive more specifics operator; it stands for the more specifics of the address prefix including the address prefix itself.  For example, 5.0.0.0/8^+ contains all the more specifics of 5.0.0.0/8 including 5.0.0.0/8.
* ^n where n is an integer, stands for all the length n specifics of the address prefix.  For example, 30.0.0.0/8^16 contains all the more specifics of 30.0.0.0/8 which are of length 16 such as 30.9.0.0/16.
* ^n-m where n and m are integers, stands for all the length n to length m specifics of the address prefix.  For example, 30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8 which are of length 24 to 32 such as 30.9.9.96/28.

## Monitors
This sections contains all monitors that will be used to provide feeds of BGP updates to the monitoring and detection components of ARTEMIS. Currently the following feeds are supported:

### [RIPE RIS](http://stream-dev.ris.ripe.net/demo2)

    riperis: ['']

Means: "select or available RIPE RIS RRCs". You can specify specific RRCs within the list if you like, as follows:

    riperis: [rrc19,rrc21]

### [BGPStream](https://bgpstream.caida.org/) (live)

Offering access to [RIPE RIS and RouteViews RRCs](https://bgpstream.caida.org/data).

    bgpstreamlive:
    - routeviews
    - ris

Means: "select all available RRCs from RouteViews, RIPE RIS and Caida projects". You can specify any or all of the three projects.

### [ExaBGP](https://github.com/Exa-Networks/exabgp)

    exabgp:
    - ip: ip_to_exabgp_1
      port: port_1
    - ...
    - ip: ip_to_exabgp_N
      port: port_N

Means: "receive feed from the N exaBGP monitors configured on these IPs and ports" (default IP="exabgp", default port=5000). To configure exaBGP sessions with your local routers please consult this [docs section](https://bgpartemis.readthedocs.io/en/latest/exabgpfeed/).

### Historical BGPStream records

    bgpstreamhist: csv_dir_with_formatted_BGP_updates

Means: "replay all recorded BGP updates found in all .csv files in this directory". W.r.t. the format of the updates in the files, please consult this [docs section](https://bgpartemis.readthedocs.io/en/latest/history/).

## Full example

    monitors:
        riperis: ['']
        bgpstreamlive:
            - routeviews
            - ris
        exabgp:
            - ip: ip_to_exabgp_1
              port: port_1
            - ...
            - ip: ip_to_exabgp_N
              port: port_N
        bgpstreamhist: csv_dir_with_formatted_BGP_updates

You can comment any monitor you do not want to be used.

For additional private BMP feeds based on bgpstreamlive and Kafka, please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/bgpstreambmp/).

## ASNs
This section contains all declared ARTEMIS ASNs. You can create ASN references by prefixing them with "&", which you can later access using the "*" prefix. You can reference both single ASNs as well as lists of ASNs.
Be careful to properly reference ASNs that you use in the rules later.

### Example

    asns:
        my_asn: &my_asn
            1234
        my_asns: &my_asns
            - 321
            - 432
        my_neighbor: &my_neighbor
            222
        my_neighbors: &my_neighbors
            - 333
            - 444

Note that you can also input ranges of ASNs, as follows:

    asns:
        my_asn_range: &my_asn_range
            - 1234-5678

(ranges can be expressed as adhering to the following regular expression: `^(\d+)\s*-\s*(\d+)$`).

You can further define and reference AS-SETs resolvable by the RIPE historical WHOIS database, by simply
adding them as follows:

    asns:
        RIPE_WHOIS_AS_SET_your_as_set_name: &RIPE_WHOIS_AS_SET_your_as_set_name
            []

On  the admin system page, by clicking the button "Load AS-SETs" next to "Edit", you can automatically load information from the remote WHOIS database and resolve the AS-SET name (you will observe that the list is automatically populated). Appropriate pop-ups will notify you about the success or failure of this operation.
You can simply reference a resolvable AS-SET as any other group of ASNs, e.g.,

    - prefixes:
          - ...
      origin_asns:
          - *RIPE_WHOIS_AS_SET_your_as_set_name
      ...


## Rules
Rules are the "heart" of the ARTEMIS configuration logic, since they constitute the operator-supplied ground truth against which ARTEMIS checks incoming BGP updates to detect hijacks. A rule is composed of the following subsections:

### Prefixes
The list of prefixes involved in this rule (can be lists themselves). Example:

    prefixes:
        - *my_prefix_1
        - ...
        - *my_prefix_N
        - *my_prefix_list

### Origin ASNs
The list of origin ASNs of the networks that are allowed to advertise the aforementioned prefixes (can be lists themselves). Example:

    origin_asns:
      - *my_asn_1
      - ...
      - *my_asn_N
      - *my_asn_list

Note that omitting this section signals ARTEMIS to check for squatting attacks (i.e., it is equivalent to a statement like "No ASN is allowed to advertise these prefixes"). However, you can also wildcard the field by using:

    origin_asns: '*'

This will monitor the selected prefixes but **will not issue any hijack alerts other than potential sub-prefix or policy violation hijacks** (where the hijacked prefix is a sub-prefix of one of the selected ones).

### Neighbors
The list of the ASNs of the neighbors of the aforementioned networks (owning the origin ASNs) that are allowed to advertise the aforementioned prefixes (can be lists themselves). Example:

    neighbors:
      - *neighbor_asn_1
      - ...
      - *neighbor_asn_N
      - *neighbor_asn_list

Note that if you want neighbor checks to be wildcarded, you can simply omit this section; however, you will not receive hijack alerts involving fake first hops since in this case, all first hops are considered legal.

### Prepend sequence matching
The pattern (seen as a prepend sequence of AS-hops) that legal origin ASes are allowed to use to advertise
their prefixes. Essentially it is the part of the path beyond the origin AS that the user/operator knows
about and uses for policy differentiation. Example:

   ```
   prepend_seq:
     - [..., AS_2, AS_1],
     - [..., AS_4, AS_3],
     - ...
   ```
The sequence is matched after properly matching the origin of the AS-path of a BGP update. If the
origin is e.g., `AS_0`, then legit BGP updates should contain paths of the form `..., AS_2, AS_1, AS_0`
or `..., AS_4, AS_3, AS_0` towards the configured prefix.

*Note: this rule configuration cannot be combined with `neighbors`, please use one or the other. Moreover,
it cannot be combined with `no-export` policies, please use one or the other.*

See [this issue](https://github.com/FORTH-ICS-INSPIRE/artemis/issues/443) for more details.

### Mitigation
The action that you want to do when you press "Mitigate" in a hijack view page. By default it is set to "manual" (even if you omit this section), which resorts to essentially nothing (ARTEMIS as a passive monitoring and detection tool). However, you can also set here the location of a script that runs the code you need, with the following requirements:

1. It should be the location of an executable

2. The executable should support the '-e' input option (mandatory), that instructs mitigation to end (if absent, then mitigation will start), as well as the '-i' input option (mandatory), that takes as input a json representation of a hijack event (provided by ARTEMIS). This representation contains the following information:

     {
         'key': unique_hijack_id,
         'prefix': hijacked_prefix
     }

     Based on this information, you can run a custom script that de-aggregates the prefix (if possible), or outsources mitigation to an external domain. **These functions are not supported for all networks, but should be custom-built by the operator, in case automated mitigation is required.**

     Do not forget to instruct the backend container (and therefore the mitigation microservice) w.r.t. the location of your script, by properly mapping this in a backend volume using the `docker-compose.yaml` file.

     Example script (e.g., under `backend/test_mitigate.py`; this should be made executable with `chmod +x`):

         #!/usr/bin/env python

         import argparse

         parser = argparse.ArgumentParser(description="test ARTEMIS mitigation")
         parser.add_argument("-i", "--info_hijack", dest="info_hijack", type=str, help="hijack event information", required=True)
         parser.add_argument("-e", "--end", dest="end_hijack", action="store_true", help="flag to indicate unimitigation")
         args = parser.parse_args()

         # write the information to a file (example script)
         with open('/root/mit.txt', 'w') as f:
         f.write(args.info_hijack)

     Example configuration file snippet:

         - prefixes: ...
           ...
           mitigation: "/root/test_mitigate.py"

     Example `docker-compose.yaml` configuration:

         configuration:
           ...
           volumes:
             ...
             - ./test_mitigate.py:/root/test_mitigate.py
             ...
         ...
         mitigation:
           ...
           volumes:
             ...
             - ./test_mitigate.py:/root/test_mitigate.py
             ...

### Policies
The policies that apply to this rule. Currently we support the no-export policy, which can be configured as follows:

    policies:
    - 'no-export'

This means that if we see a path with length > 3, of the form:

    [monitor, other_as, neighbor, origin]

ARTEMIS triggers an alert on the 4th hijack dimension (policies), since this means that the neighbor of the origin leaked the prefix to an AS that it should not. Paths with length <= 3 are not triggering any alerts since such paths:

    [monitor, neighbor, origin]

are considered benign (the neighbor is allowed to export the route to a passive monitoring service). **NOTE: since this is a new feature, we would appreciate feedback on how it should work in different operational environments.** You can also omit this section, if not of interest to your setup.

### Community annotations
The community annotations applying to possible hijacks to which this rule applies. Please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/commannotations/) for more information.

Full example (except for community annotations, which is an experimental feature):

    - prefixes:
        - *my_prefix_list
      origin_asns:
        - *my_asn_list
      neighbors:
        - *my_neighbor_list
      mitigation: manual


### Examples

#### Fake origin (+ exact-prefix): E|0|-|-
Rule:

    - prefixes:
        - prefix_A
      origin_asns:
        - ASN_A
      neighbors:
        - ASN_B
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [..., ASN_C]:prefix_A

Sample legal BGP update:

    [..., ASN_B, ASN_A]:prefix_A

#### Legal origin, fake first hop neighbor (+exact-prefix): E|1|-|-
Rule:

    - prefixes:
        - prefix_A
      origin_asns:
        - ASN_A
      neighbors:
        - ASN_B
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [..., ASN_C, ASN_A]: prefix_A

Sample legal BGP update:

    [..., ASN_B, ASN_A]: prefix_A

#### Legal origin, fake prepend sequence pattern (+exact-prefix): E|P|-|-
Rule:

    - prefixes:
        - prefix_A
      origin_asns:
        - ASN_A
      prepend_seq:
        - [ASN_C, ASN_B]
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [..., ASN_D, ASN_A]: prefix_A

Sample legal BGP update:

    [..., ASN_C, ASN_B, ASN_A]: prefix_A

#### Sub-prefix: S|<code>&ast;</code>|-|-
Rule:

    - prefixes:
        - prefix_A
      origin_asns:
        - ASN_A
      neighbors:
        - ASN_B
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [...]:sub_prefix_A

Sample legal BGP update:

    [..., ASN_B, ASN_A]:prefix_A

#### Squatting: Q|0|-|-
Rule:

    - prefixes:
        - prefix_A
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [...]:prefix_A

Sample legal BGP update:

    None

#### No export policy violation: : <code>&ast;</code>|<code>&ast;</code>|-|L
Rule:

    - prefixes:
        - prefix_A
      origin_asns:
        - ASN_A
      neighbors:
        - ASN_B
      policies:
        - 'no-export'
      mitigation: manual

Sample BGP update triggering a hijack alert:

    [..., ASN_D, ASN_B, ASN_A]:prefix_A

Sample legal BGP update:

    [ASN_D, ASN_B, ASN_A]:prefix_A

(*Note: ASN_D is considered OK for export as the used monitor, so the latter 3-hop path does not trigger an alert*)

#### Legal wildcarded origin (with sub-prefix hijack)
Rule:

    - prefixes:
        - prefix_A
      origin_asns: '*'
      mitigation: manual

Sample BGP update triggering the hijack:

    [...]:sub_prefix_A

Sample legal BGP update:

    [...]:prefix_A

### Caveats and Tips
**Note**: if there are different combinations of origin(s)-neighbor(s) for a prefix (or prefixes), please consider breaking into multiple rules to avoid an erroneous cross-product check. For example, assume that you advertise prefix P from origin A with neighbor B, and from origin C with neighbor D. If you configure:

    - prefixes:
          - prefix_A
      origin_asns:
          - ASN_A
          - ASN_C
      neighbors:
          - ASN_B
          - ASN_D
      ...

then the combinations ASN_A-ASN_D and ASN_C-ASN_B are also considered legal, even if they do not exist in reality! The correct way to configure ARTEMIS in that case would be using 2 rules:

    - prefixes:
          - prefix_A
      origin_asns:
          - ASN_A
      neighbors:
          - ASN_B
      ...
    ...
    - prefixes:
          - prefix_A
      origin_asns:
          - ASN_C
      neighbors:
          - ASN_D
      ...

## Auto-populating the configuration file

While this is a custom feature that needs to be handled by the ARTEMIS deployer (and is not provided by the open-source software as a service), we are offering a few utility functions that can be used by the user to generate yaml configurations in [this file](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/utils/artemis_utils/conf_lib.py). The documentation of each function can be found below.

**We recommend though that you write your own custom scripts and functions based on your local setup. The requirements for being able to generate yaml from custom sources are the `json` and `ruamel.yaml` pip packages.**

### Creating prefix definitions

create_prefix_defs(yaml_conf, prefixes)


INPUT: prepared yaml conf (see code) + dict of prefixes:

    prefixes: {
      "10.0.0.0/24": "my_prefix"
    }

OUTPUT:

    ...
    prefixes:
      my_prefix: &my_prefix
        - 10.0.0.0/24
    ...

### Creating monitor definitions

create_monitor_defs(yaml_conf, monitors)

This can be customized at will, please check the code.

INPUT: prepared yaml conf (see code)

OUTPUT:

    ...
    monitors:
      riperis: ['']
      bgpstreamlive:
        - routeviews
        - ris
    ...

### Creating ASN definitions

create_asn_defs(yaml_conf, asns)

INPUT: prepared yaml conf (see code) + dict of ASNs, including optional asn group information:

    asns: {
      1234: ("AS_1234", "PEER_GROUP_X"),
      5678: ("AS_5678", "PEER_GROUP_X"),
      9012: ("AS_9012", None)
    }

OUTPUT:

    ...
    asns:
      PEER_GROUP_X: &PEER_GROUP_X
        - 1234
        - 5678
      AS_9012: &AS_9012
        - 9012
    ...

### Creating Rule definitions

create_rule_defs(yaml_conf, prefixes, asns, prefix_pols, mitigation_script_path="manual")

INPUT: prepared yaml conf (see code) + dict of prefixes (see above) + dict of ASNs (see above) + dict of prefix policies:

    prefix_pols: {
      "10.0.0.0/24": [{
        "origins": [9012] # these need to be standalone ASNs, not groups
        "neighbors": [1234, 5678] # can be a standone asn, but if it is in a group, the whole group is added (like in this case; it suffices to declare one asn from a group)
      }]
    }

OUTPUT:

    ...
    rules:
    - prefixes:
        - *my_prefix
      origin_asns:
        - *AS_9012
      neighbors:
        - *PEER_GROUP_X
      mitigation:
        manual
    ...


## Autoignore

This feature enables the user to define "autoignore" rules for his/her prefix(es), which instruct ARTEMIS to automatically ignore hijack alerts that are "stale" and of low impact/visibility. The user can add the following section (autoignore rule dictionary) to the configuration file (reserved keywords are in bold font):

    ...
    autoignore:
      autoignore_non_important_prefixes: &autoignore_non_important_prefixes
        thres_num_peers_seen: "number of peers seen the hijack below which alert should be ignored (int)"
        thres_num_ases_infected: "number of infected ASes below which alert should be ignored (int)"
        interval: "time passed since last hijack update (seconds, int)"
        prefixes:
        - *prefix_group_1
        - ...
      autoignore_...
    ...

The underlying mechanism takes care of periodically (according to the interval) checking hijack alerts that have low impact and low visibility. The pseudocode of the mechanism (which is transparent to the user) is as follows:

    if (alert.prefix.best_match(autoignore.ruleX.prefixes)) and
       (time_now - alert.time_last_updated > autoignore.ruleX.interval) and
       (alert.num_peers_seen < autoignore.ruleX.thres_num_peers_seen) and
       (num_asns_inf < autoignore.ruleX.thres_num_ases_infected):
          alert.ignore()
