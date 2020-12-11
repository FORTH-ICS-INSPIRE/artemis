## Issues and Fixes
* IPv4 DNS resolvers

For the RIPE RIS monitors to work, you need to have an IPv4 DNS resolver on the machine that runs the backend docker container.

* Browser support and compatibility

Some older version of browsers do not use session cookies by default on the Fetch API. This means that communication with GraphQL will not work and you will have parseJSON syntax error on the console of the browser.

To fix this, either update your browser or download the newest version of the tool.

* Storage of ARTEMIS on NFS

Due to time-sensitive operations in DB and continuous interaction with the rest of the system, it is strongly discouraged to deploy Artemis on a VM where the VM’s virtual disk resides on an NFS based storage system. NFS has been proved to be a bottleneck when Artemis tries to apply operations in the DB, which results on degradation of performance and numerous false positive alarms.

If deployed in a VM, we encourage you to use local storage for the VM’s HDD. This deployment can guarantee proper processing of the BGP updates on time.

**ATTENTION: use [RFC2622 operators](https://bgpartemis.readthedocs.io/en/latest/basicconf/#prefixes) wisely, while they are easy to express they may represent billions of prefixes underneath!**
