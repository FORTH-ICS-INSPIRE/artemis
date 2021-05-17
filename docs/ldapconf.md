You can configure LDAP as an authentication method. You need to change the following variables in the `.env` file:

```
LDAP_ENABLED=true                                             # Whether LDAP auth is enabled
LDAP_HOST=ldap                                                # LDAP auth host (set by default to the used microservice)
LDAP_PORT=10389                                               # LDAP bind port
LDAP_PROTOCOL=ldap                                            # LDAP protocol
LDAP_BIND_DN="cn=admin,dc=planetexpress,dc=com"               # Bind Domain with user that will be used for queries
LDAP_BIND_SECRET="GoodNewsEveryone"                           # Bind secret
LDAP_SEARCH_BASE="ou=people,dc=planetexpress,dc=com"          # Search base domain that will be used for authentication
LDAP_SEARCH_FILTER="(mail={{username}})"                      # Which filter will be searched/queried (email by default)
LDAP_SEARCH_ATTRIBUTES="mail, uid"                            # Search attributes
LDAP_EMAIL_FIELDNAME=mail                                     # Fieldname for email
LDAP_ADMIN_GROUP=admin_staff                                  # Admin group
LDAP_USER_GROUP=                                              # User group
```
