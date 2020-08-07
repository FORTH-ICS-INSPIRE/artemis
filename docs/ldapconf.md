You can configure LDAP as an authentication method. You need to change the following variables in the `/frontend/webapp/configs/webapp.cfg` file:

```
AUTH_METHOD = "ldap"                                          # Define AUTH method

SECURITY_LDAP_URI = "ldap"                                    # URL for the LDAP server
SECURITY_LDAP_BASE_DN = "ou=People,dc=example,dc=org"         # Base Domain that will be used for authentication
SECURITY_LDAP_SEARCH_FILTER = "(mail={})"                     # Which field will be queried (email by default)
SECURITY_LDAP_BIND_DN = "cn=admin,dc=example,dc=org"          # Bind Domain with user that will be used for queries
SECURITY_LDAP_BIND_PASSWORD = "admin"                         # Password of the user that will be doing the queries
SECURITY_LDAP_EMAIL_FIELDNAME = "mail"                        # Fieldname for email
SECURITY_LDAP_ADMIN_GROUPS_FIELDNAME = "objectClass"          # Fieldname group that will seperate users from admins
SECURITY_LDAP_ADMIN_GROUPS = ["top"]                          # Admin groups name
```
