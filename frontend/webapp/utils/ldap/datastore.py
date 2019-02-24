"""Connects Flask-Security datastore to LDAP."""
import ldap3
from flask_security.datastore import SQLAlchemyUserDatastore
from flask_security.utils import config_value
from ldap3.core.exceptions import LDAPExceptionError


class LDAPUserDatastore(SQLAlchemyUserDatastore):
    """Provide datastore based on Flask Security's SQLAlchemyDatastore."""

    def __init__(self, db, user_model, role_model):
        """Init new datastore given user and role models."""
        SQLAlchemyUserDatastore.__init__(self, db, user_model, role_model)

    def _get_ldap_con(self):
        server = ldap3.Server(config_value("LDAP_URI"), connect_timeout=1)
        con = ldap3.Connection(
            server,
            user=config_value("LDAP_BIND_DN"),
            password=config_value("LDAP_BIND_PASSWORD"),
            receive_timeout=True,
        )
        con.bind()
        return con

    def _close_ldap_con(self, con):
        con.unbind()

    def query_ldap_user(self, identifier):
        """Get information about a user throught AD."""
        con = self._get_ldap_con()

        result = con.search(
            search_base=config_value("LDAP_BASE_DN"),
            search_filter=config_value("LDAP_SEARCH_FILTER").format(identifier),
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES,
        )

        data = con.entries
        self._close_ldap_con(con)

        if result and data:
            return (data[0]["DistinguishedName"].value, data[0])
        else:
            raise LDAPExceptionError("User not found in LDAP")

    def verify_password(self, user_dn, password):
        """Attempt to authenticate against AD."""
        con = self._get_ldap_con()
        valid = True
        try:
            valid = con.rebind(user=user_dn, password=password)
        except ldap3.LDAPBindError:
            valid = False
        self._close_ldap_con(con)
        return valid
