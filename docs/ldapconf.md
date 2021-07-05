You can configure LDAP as an authentication method. You need to change the following variables in the `.env` file:

```
LDAP_ENABLED=true                                             # Whether LDAP auth is enabled
LDAP_HOST=ldap                                                # LDAP auth host (set by default to the used microservice; you can set it to your actual host)
LDAP_PORT=10389                                               # LDAP bind port
LDAP_PROTOCOL=ldap                                            # LDAP protocol (alternative: ldaps)
LDAP_BIND_DN=cn=admin,dc=planetexpress,dc=com               # [OPTIONAL] Bind Domain with user that will be used for queries
LDAP_BIND_SECRET=GoodNewsEveryone                           # [OPTIONAL] Bind secret for user that will be used for queries
LDAP_SEARCH_BASE=ou=people,dc=planetexpress,dc=com          # Search base domain that will be used for authentication
LDAP_SEARCH_FILTER=(mail={{username}})                      # Which filter will be searched/queried (email by default)
LDAP_SEARCH_ATTRIBUTES=mail,uid                            # Search attributes
LDAP_GROUP_SEARCH_BASE=ou=people,dc=planetexpress,dc=com    # [OPTIONAL] The base DN from which to search for groups. If defined, also groupSearchFilter must be defined for the search to work.
LDAP_GROUP_SEARCH_FILTER=(member={{dn}})                    # [OPTIONAL] LDAP search filter for groups (alternative: (uniqueMember={{dn}})).
LDAP_GROUP_SEARCH_ATTRIBUTES=mail,uid                       # [OPTIONAL] default all. Array of attributes to fetch from LDAP server (alternative: cn).
LDAP_EMAIL_FIELDNAME=mail                                     # Fieldname for email
LDAP_ADMIN_GROUP=admin_staff                                  # Admin group (use "," separation for multiple groups)
```
