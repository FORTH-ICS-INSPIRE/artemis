# Frequently Asked Questions

## ARTEMIS observed and notified a new hijack alert. What should I do next?

A sample workflow would be:

1) Verify hijack locally (e.g., by checking whether another team announced something that was not planned in case the origin is legal),

2) Check possible mitigation countermeasures (such as contacting the upstreams of the offending AS for filtering).

**Request to community: please extend this workflow with your favorite flavor! How do you deal with such alerts in practice?**

## How do I enable selective logging of BGP hijacks, based on certain attributes?

Please check out [this docs page](https://bgpartemis.readthedocs.io/en/latest/commannotations/), which describes how you can use communities to instruct ARTEMIS to automatically annotated hijack alerts (e.g., based on their criticality), and log only the alerts that you consider of certain importance.

## How do I enable selective logging of BGP hijack fields on new alerts?

Please check out [this docs page](https://bgpartemis.readthedocs.io/en/latest/envvars/), which provides a sample for the `HIJACK_LOG_FIELDS` variable; this dictates what fields should be present in the logged messages. Note that as an extension of the response to Q (2), you can also tune the previous log filter to filter log messages based on certain values of certain fields (e.g., "log only hijack alerts that are related to this hijack AS"; though not probably an extremely useful option in practice, we believe that it can be of use when more advanced filters are added in the future, e.g., "log only messages hijack alerts that have been observed by at least 100 ARTEMIS monitor peers, etc.").

## I see a lot of incoming load on the BGP updates; ARTEMIS is not able to process them at line-rate and the load is constantly accumulating. What should I do?

The main approach to deal with this is to distribute the detection load to multiple detectors,
prefix trees and database access (db client) microservices to read in parallel (writing may be
unfortunately be a bottleneck). See [this docs section](https://bgpartemis.readthedocs.io/en/latest/scaling/)
on how to spawn multiple microservices using `docker-compose` scaling capabilities.

## I know for a fact that a hijack against one of my prefixes took place, but ARTEMIS did not detect it. What are the potential reasons for this?

There can be several reasons for this happening:

1) it was a very low-impact event (e.g., affected less than 2% of the AS-level Internet);
   public monitoring services may offer limited visibility on such events.
   Typically, sub-prefix events are way more visible than exact-prefix hijacks;
   in the latter case, hijack BGP updates may reach a very small subset of the Internet.

2) the ARTEMIS detection service was OFF at the time the BGP update reached the monitoring service
   (do not forget that ARTEMIS is designed as a stream processor; missed BGP updates will stay in the
   past, and will not be replayed so that ARTEMIS can keep offering a truly real-time experience).

3) The ARTEMIS operational prefix itself was hijacked! This means that the hijacker may have isolated
   ARTEMIS from the public monitoring services it uses. Please check best practice
   (1) on [this docs page](https://bgpartemis.readthedocs.io/en/latest/bestpractices/)
   for countermeasures against such happenings.

4) The hijack is of a type currently non-detectable by ARTEMIS, e.g., E|-|-|- (i.e.,
   the hijacker is deeper than one hop in the path, potentially advertising a fake link).
   We plan to add support for such events in the future (Type-N, N>=2 detection is under
   research at this time).

## I want to connect ARTEMIS frontend to my LDAP server. How can I do that?

We support custom LDAP connectivity for the ARTEMIS frontend; please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/ldapconf/) for details.

## My database has reached large sizes (million+ of BGP updates) within a very small amount of time (hours/days). What are the potential reasons and countermeasures for that?

Apparently your network's prefixes are very active in BGP :) . We advise to take advantage of the "auto-clean" features of ARTEMIS; see auto-cleaning information on [this docs page](https://bgpartemis.readthedocs.io/en/latest/bestpractices/). Moreover, please tend to ongoing alerts timely (learning them via the auto-learning features of ARETMIS or updating the configuration in case of false positives); letting erroneous alerts absorb BGP updates is not advisable.

## How can I contribute to the ARTEMIS project?

We are very happy that you ask this question :)! We happily accept contributions in software; please check [this GitHub page](https://github.com/FORTH-ICS-INSPIRE/artemis/issues) for issues that need care and love ;) . All our milestones are listed on [this GitHub page](https://github.com/FORTH-ICS-INSPIRE/artemis/milestones). Please feel free to create new relevant issues too; you can open either feature requests or bug fixes. As always, we are highly interested in real-worlds operational advice and experiences (or pains) with BGP hijacks at scale; tales from the field are excellent motivators!

## I possess a Kubernetes cluster which I can use for pod deployment. Can I deploy ARTEMIS there, and how?

Yes! Please consult [this docs page](https://bgpartemis.readthedocs.io/en/latest/kubernetes/) for sample setup instructions. Since we do not have significant expertise with Kubernetes (except for one member of our dev team who has deployed K8s clusters in the wild), advice to improve things is more than welcome!

## My ARTEMIS instance has run into out-of-memory issues. What are the possible causes for this?

Too much configuration load, too little memory! First, count (preferably automatically) the number of configured prefixes/rules you are using. According to this number and the number of prefixtree modules that you spawn, please follow
memory allocation guidelines described in detail [here](https://bgpartemis.readthedocs.io/en/latest/requirements/#memory-requirements).

## How do I upgrade the ARTEMIS software?

It is quite easy! Please check [this docs section](https://bgpartemis.readthedocs.io/en/latest/upgrade/) for
details. In general, these are the 3 key things to remember:

1) shut down ARTEMIS

2) pull via `git`, to synchronize `.env`, `docker-compose` and other needed files (and resolve any conflict is needed). Note that you can also checkout specific releases (check out available git tags), but be careful to always upgrade (and pull the corresponding containers after the appropriate `.env` file is updated)!

3) pull via `docker-compose` to synchronize containers

After these steps, just spin ARTEMIS anew; DB migrations and other updates will take place automatically.

## How do I easily incorporate my changes withing the .env and docker-compose.yaml files after an upgrade overwrites them?

Upgrades do not simply overwrite these files, but may cause git conflicts that need to be resolved by the user; they are under version control on purpose (in contrast e.g., to customer-side `local_configs` files), since we often update them with new variables, microservices, etc. The simplest advice is to resolve potential conflicts locally; before you pull from git , do a `git stash`, pull and then `git stash pop`. Resolve conflicts, `git reset .` and spin ARTEMIS!

## I'm getting "Bad gateway" when trying to reach the webpage after a docker-compose up -d.  What happened?

 Typically this may be because ARTEMIS is still booting its different microservices; the frontend depends on other microservices that need to boot first (see dependencies in `docker-compose.yaml`). Therefore, especially if you have deployments with "large" configurations (e.g., millions of configured IPv4/IPv6 routes), just wait for a few minutes; eventually the frontend, and the frontend's frontend :) NGINX should be up and running, routing user requests to ARTEMIS UI. If the problem persists even after several minutes, this might be a hint of a misconfigured `docker-compose.yaml` file or another problem with the local `dockerd`. Please contact ARTEMIS team on slack and share useful logs (`docker-compose logs -f ...`), either on the "issues" channel or via PM.

## How do I connect ARTEMIS to my local routers/route collectors for monitoring?

We use exaBGP for this. Please consult [this docs section](https://bgpartemis.readthedocs.io/en/latest/exabgpfeed/) for details.

## Can I replay historical BGP updates? If yes, how?

Yes! Please consult [this docs section](https://bgpartemis.readthedocs.io/en/latest/history/) for details.

## My network policies are very complex! Can you help me build the configuration file?

Typically we do not provide case-by-case consultation (since we provide the open-source tool, but not a paid consultation service), but we have built an auto-configuration feature that will help you a lot, essentially taking care of keeping up-to-date with all your local changes! Please follow [this docs page](https://bgpartemis.readthedocs.io/en/latest/autoconfiguration/).

## How can I check the RPKI status of my hijacked prefixes?

Please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/rpkivalidconf/). You can use either your own RPKI validator or spawn routinator as an ARTEMIS microservice.

## I have a private BMP feed in `kafka`, and would like to export it to ARTEMIS. How can I do this?

Please check [this docs page](https://bgpartemis.readthedocs.io/en/latest/bgpstreambmp/).

## I am not receiving updates and my error log contains messages like `Failure when receiving data from the peer (56)` or `parse_ripe_ris: RIPE RIS Server closed connection. Restarting socket in X seconds`

Some users may experience issues receiving updates for a range of reasons, and error messages like this point to a network problem.

If you can see errors with receiving data or downloading resources within your docker logs, the following steps my help you uncover the source of your issue.

1. Verify that you can download the updates from your Host OS. If you can’t, remedy this issue. Your host firewall, or docker host may not be correctly configured. It is also possible that the resource you are trying to access may genuinely be unavailable at this time.
2. Verify whether you can retrieve the downloads from a basic Docker container. You could use the ‘curlimages/curl’ image if you do not have another locally (e.g. `docker run -i -t curlimages/curl:latest curl <url>`). If you can, your Docker environment is working and your issue is likely to be configuration. You may want to recreate your Artemis containers (`docker-compose down`, `docker-compose up -d`) and try again.
3. Check the MTU on your Docker/Host and ensure they are consistent. If your host has an MTU that is lower than the Docker MTU, you may have issues with packet fragmentation which in turn can cause download failures.
4. Otherwise, it is probably a transient server-side issue.
