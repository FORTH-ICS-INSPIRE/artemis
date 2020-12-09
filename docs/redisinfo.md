Information stored in Redis:

**TODO: recheck keys in new architecture**

| key format | value type | value | description |
|:---:|:---:|:---:|:---:|
| [a-z0-9]{32}                          | string    | dictionary        | hijack ephemeral key with all details in value      |
| [a-z0-9]{32}                          | string    | "1" or None       | BGP update persistent key                           |
| [a-z0-9]{32}token_active              | string    | "1" or "0"        | track if token is active                            |
| [a-z0-9]{32}token                     | list      | "token"           | used with BLPOP like a mutex for hijack processing  |
| hijack_[a-z0-9]{32}_prefixes_peers    | set       | "prefix_peerASN"  | get prefixes and peer ASes from ephemeral hijack key|
| hij_orig_neighb_[a-z0-9]{32}          | set       | "origin_neighbor" | store origin-neighbor pairs per hijack              |
| prefix_$PREFIX_peer_$ASN_hijacks      | set       | "hijack key"      | store the hijack keys for this prefix and peer asn  |
| $SERVICE_seen_bgp_update              | string    | "1" or none       | check if we saw update the last X minutes           |
| peer-asns                             | set       | ASNs              | peer ASNs as numbers                                |
| last_handled_timestamp                | string    | timestamp         | last BGP update handled timestamp                   |
| persistent-keys                       | set       | "hijack_key"      | persistent hijack keys                              |
| redis-bootstrap                       | string    | "1" or None       | signal if redis is bootstrapped by DB               |
