Table of Contents

* [BGP hijack information](#bgp-hijack-information)
* [Classification of hijacks](#classification-of-hijacks)
* [Hijack states](#hijack-states)
* [Hijack actions](#hijack-actions)
* [Example workflows](#example-workflows)

## BGP hijack information
* **Time Detected**:
  The time when a hijack event was first detected by the system.
* **Status**:
  See [Hijack states](#hijack-states).
* **Prefix** (IPv4/IPv6):
  The hijacked prefix.
* **Type**:
  See [Classification of hijacks](#classification-of-hijacks).
* **Hijacker AS**:
  The AS that is possibly responsible for the hijack (*note that this is an experimental field*).
* **RPKI**:
  The RPKI status of the hijacked prefix. Can be:
  ```
  "NA" → Non Applicable
  "VD" → Valid
  "IA" → Invalid ASN
  "IL" → Invalid Prefix Length
  "IU" → Invalid Unknown
  "NF" → Not found
  ```
* **Number of Peers Seen**:
  Number of peers/monitors (i.e., ASes) that have seen hijack updates.
* **Number of ASes Infected**:
  Nmber of infected ASes that seem to route traffic towards the hijacker AS, according to control plane information (*note that this is an experimental field*).
* Additional information under "More" tab:
    * **Matched**:
      The prefix that was (best) matched in the configuration (*note: this might differ from the actually hijacked prefix in the case of sub-prefix hijacks*).
    * **Config**:
      The timestamp (i.e., unique ID) of the configuration based on which this hijack event was triggered.
    * **Key**:
      The unique key of a hijack event.
    * **Time Started**:
      The timestamp of the oldest known (to the system) BGP update that is related to the hijack.
    * **Time Ended**:
      The timestamp when the hijack was ended. It can be set in the following ways: (i) manually, when the user presses
      the "resolved" button; (ii) automatically, when a hijack is completely withdrawn (all monitors that saw hijack
      updates for a certain prefix have seen the respective withdrawals). Note that in the latter case, withdrawals can be "implicit", i.e., they stem due to corrected AS-paths towards the advertised IP prefix.
    * **Last Update**:
      The timestamp of the newest known (to the system) BGP update that is related to the hijack.
    * **Mitigation Started**:
      The timestamp when the mitigation was triggered by the user ("mitigate" button).
    * **Display Peers**:
      The peer/monitors that either saw hijack updates, or received explicit withdrawals of the hijacked prefix.
    * **Comment**:
      Text written by the user (accompanies the hijack event).
    * **Related BGP Updates**:
      Table with the BGP updates (both announcements and withdrawals) that are related to the hijack event (information
      is the same as [here](https://bgpartemis.readthedocs.io/en/latest/bgpupdateinfo/)).
    * **Community Annotation**: The user-defined annotation of the hijack according to the communities of hijacked BGP updates.

## Classification of hijacks
In general, we classify hijack events according to the 3D taxonomy that we describe in [our paper](https://www.inspire.edu.gr/wp-content/pdfs/artemis_TON2018.pdf), plus an additional "policy violation" dimension, as we explain in the following.

### Prefix dimension
How a hijacker manipulates a prefix. Can be:

* **Sub-prefix (S)** hijack: the attacker announces a sub-prefix of a configured super-prefix.
* **Exact-prefix (E)** hijack: the attacker announces a prefix that matches exactly a configured prefix (*note that the E dimension alone does not indicate a hijack!*).
* **sQuatting (Q)** hijack: the attacker announces a prefix that is not supposed to be seen on the public Internet control plane.

### (AS-)Path dimension
How a hijacker manipulates the path to a prefix. Can be:

* **Type-0 (0)** hijack: the attacker announces a path with an illegal origin.
* **Type-1 (1)** hijack: the attacker announces a path with a legal origin, but illegal first hop.
* **Type-N (N)** hijack: the attacker fakes a link deep in the path (N=2: the 2nd hop is illegal, N=3: the 3rd hop is illegal, etc.)
* **Type-P (P)** hijack: the attacker fakes a prepend sequence pattern in the AS-path (not related to type-N hijack; pattern can be an entire sequence of hops)
* **Type-U (U)** hijack: the attacker does not change the path at all (can be combined with a sub-prefix hijack).

Currently, ARTEMIS issues '-' for Type-N/U attacks (not supported).

### Data plane dimension
How an attacker manipulates the traffic leading to a prefix. Can be:

* **Blackholing (B)** hijack: the attacker drops packets en-route.
* **Imposture (I)** hijack: the attacker impersonates the services of a victim.
* **Man-in-the-Middle (M)** hijack: the attacker intercepts (and potentially alters) traffic en-route.

Currently, ARTEMIS issues '-' for these types of attacks (control-plane tool).

### Policy dimension
How an attacker manipulates BGP policies related to a prefix. Can be:

* **Route leak due to no-export violation (L)** hijack: the attacker announces a no-export route to another (non-monitor) AS.

Currently, besides 'L' (no-export violations), ARTEMIS issues '-' for other types of policy violations.


### Combinining dimensions
In general, any potential hijack can be represented as a combination of the aforementioned dimensions:
```
Prefix | Path | Data plane | Policy
```
ARTEMIS currently detects the following combinations:

* **S|0|-|-**: sub-prefix announced by illegal origin.
* **S|0|-|L**: sub-prefix announced by illegal origin and no-export policy violation.
* **S|1|-|-**: sub-prefix announced by seemingly legal origin, but with an illegal first hop.
* **S|1|-|L**: sub-prefix announced by seemingly legal origin, but with an illegal first hop and no-export policy violation.
* **S|P|-|-**: sub-prefix announced by seemingly legal origin, but with an illegal hop pattern.
* **S|-|-|-**: not S|0|- or S|1|-, potential type-N or type-U hijack.
* **S|-|-|L**: not S|0|- or S|1|-, potential type-N or type-U hijack and no-export policy violation.
* **E|0|-|-**: exact-prefix announced by illegal origin.
* **E|0|-|-|L**: exact-prefix announced by illegal origin and no-export policy violation.
* **E|1|-|-**: exact-prefix announced by seemingly legal origin, but with an illegal first hop.
* **E|P|-|-**: exact-prefix announced by seemingly legal origin, but with an illegal hop pattern.
* **E|1|-|L**: exact-prefix announced by seemingly legal origin, but with an illegal first hop and no-export policy violation.
* **Q|0|-|-**: squatting hijack (is always '0' on the path dimension since any origin is illegal).
* **Q|0|-|L**: squatting hijack (is always '0' on the path dimension since any origin is illegal) and no-export policy violation.
* **E|-|-|-**: *not a hijack.*
* **E|-|-|L**: no-export policy violation.

## Hijack states
* **Ongoing**:
  The hijack has not been ignored, resolved or withdrawn. It is set automatically for every active hijack.
* **Dormant**:
  The hijack is ongoing, but not updated within the last X hours (see .env "DB_HIJACK_DORMANT" variable). If a new BGP update related to the hijack is received, the dormant status is discarded and the timer starts again anew.
* **Under mitigation**:
  The hijack is currently under mitigation. This is set when user presses the "mitigate" button.
* **Ignored**:
  The event is either ignored by the user (implicit false positive, requires configuration update), or has been auto-ignored due to limited visibility/impact.
* **Resolved**:
  The event is resolved by the user (implicit true positive).
* **Withdrawn**:
  All monitors that saw hijack updates for a certain (hijacked) prefix have seen the respective withdrawals. Note that withdrawals can be "implicit", i.e., they stem due to corrected AS-paths towards the advertised IP prefix. The field is set automatically.
* **Outdated**:
  The event was triggered by a configuration that is now deprecated, i.e., the hijack is no longer active according to
  the current configuration (all related hijack updates are now benign). It is set automatically.

Note that **Acknowledged** is a special (orthogonal) state denoting whether a hijack event is considered a true or false positive by the administrator. Note that an ongoing not acknowledged hijack is not necessarily a false positive (in fact, if the configuration is correct and complete, it is 100% a true positive). However, only the user can explicitly mark this.

Allowed state transitions (parenthesis denotes optional states):
* ongoing (<--> dormant) (--> under mitigation) (--> outdated/withdrawn) --> resolved
* ongoing (<--> dormant) (--> under mitigation) (--> outdated/withdrawn) --> ignored

## Hijack actions
Upon viewing a selected hijack event, the ADMIN user can execute the following actions:

* **Mitigate**:
  Start the mitigation process for this hijack. It sets the Mitigation Started field and sets an ongoing hijack to
  under mitigation state. A mitigate action is an implicit confirmation of the hijack
  event as a true positive (sets "acknowledge" to true). Note that the mitigation micro-service should be active for
  the action to work.
* **Resolve**:
  The hijack has finished (by successful mitigation or other actions). It marks the Time Ended field and sets an
  ongoing or under mitigation hijack to resolved state. A resolve action is an implicit confirmation of the hijack
  event as a true positive (sets "acknowledge" to true). If the hijack is in withdrawn or outdated state already, it is
  appended as another state tag.
* **Ignore**:
  The hijack may have finished or not, but the user chooses to ignore it. It sets an ongoing or under mitigation hijack
  to ignored state. An ignore action is an implicit confirmation of the hijack event as a false positive (sets
  "acknowledge" to false). If the hijack is in withdrawn or outdated state already, it is appended as another state
  tag. **Note 1: We have introduced a mechanism to "learn" the prefix(es), ASN(s) and rule(s) pertaining to an ongoing hijack that is to be ignored. In particular, we show the configuration diff to the user (ADMIN), before applying any changes, and the user may choose to approve the changes or ignore them. This mechanism applies only to ongoing (e.g., not outdated or withdrawn) hijacks. Note 2: We have introduced a mechanism to "auto-ignore" a hijack alert in case its impact (infected ASes) and visibility (seen peers) remain under user-specified thresholds for a user-specified period of time. For more details, check [this page](https://bgpartemis.readthedocs.io/en/latest/basicconf/#autoignore).**
* **Acknowledge**:
  Mark the hijack as a true positive (orthogonal to the other actions). When it is set to false it is considered a
  false positive until mitigated, resolved or marked explicitly. Note that acknowledging a hijack does not change any
  of its other states (e.g., if it is ongoing, it remains so).
* **Delete**: This action will delete the hijack and all BGP messages related to it. Be cautious when deleting a hijack as this action cannot be undone.

**NOTE: Every hijack event should eventually be either resolved or ignored by an ADMIN user (or it can be auto-ignored by the system in case of limited impact/visibility).**

The VIEWER use can see the status of a hijack but cannot execute any actions (e.g., activate any buttons).

## Example workflows
**UNDER CONSTRUCTION! HELP FROM OPERATORS IS NEEDED TO FILL IN THIS SECTION!!!**

### Example 1: S|0|-|- hijack with manual mitigation

1. Operator configures ARTEMIS rule:
   TBD
2. ARTEMIS receives a BGP update of the form:
   TBD
3. A hijack of type ... is generated.
4. The operator is...

TBD

### Example 2: False E|0|-|- hijack (false configuration)
TBD
