This is a Proof of Concept (PoC) implementation of a mitigation setup to be used with ARTEMIS.

We include a script that receives the information of the hijack (id + prefix), and upon
execution advertises the two subnets of the prefix performing deaggregation.

The setup is as follows:

```
 ----------------          --------------          --------------
|ARTEMIS + ExaBGP|        |    PEER AS   |        |  EXTERNAL AS |
|    AS65001     |  eBGP  |    AS65002   |  eBGP  |    AS65003   |
|      exa       | ------ |  r02 (goBGP) | ------ |  r03 (goBGP) |
|    1.1.1.10    |        |    1.1.1.2   |        |    1.1.1.3   |
 ----------------          --------------          --------------
```

We trigger the mitigation script from a PoC container and let the announcements propagate.
