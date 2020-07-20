"""Connects Flask-Security datastore to RADIUS."""
import os

from pyrad.client import Client
from pyrad.packet import AccessAccept, AccessRequest
from pyrad.dictionary import Dictionary
from flask_security.datastore import SQLAlchemyUserDatastore
from flask_security.utils import config_value
from flask import current_app
from itertools import cycle


class RADIUSUserDatastore(SQLAlchemyUserDatastore):
    """Provide datastore based on Flask Security's SQLAlchemyDatastore."""

    def __init__(self, db, user_model, role_model):
        """Init new datastore given user and role models."""
        SQLAlchemyUserDatastore.__init__(self, db, user_model, role_model)

        log = current_app.artemis_logger

        self.role_mapping = config_value("RADIUS_ROLE_MAPPING", default=None)
        self.role_attribute_code = config_value("RADIUS_ROLE_ATTRIBUTE_CODE", default=None)
        try:
            self.role_attribute_code = int(self.role_attribute_code) if self.role_attribute_code is not None else None
        except ValueError:
            raise Exception("RADIUS_ROLE_ATTRIBUTE_CODE must be a number (was %s)" % self.role_attribute_code)

        self.default_role = config_value("RADIUS_DEFAULT_ROLE", default="user")
        servers = self._create_radius_clients(config_value("RADIUS_SERVERS", default=[]))
        self.client_iterator = cycle(servers)
        self.client_attempts = len(servers)
        try:
            self.current_client = next(self.client_iterator)
            log.info("Radius servers configured. First server to try is %s:%s" % (
                self.current_client.server, self.current_client.authport))
        except StopIteration:
            raise Exception("No radius servers defined but RADIUS auth is enabled!")

    def authenticate(self, username, password):
        """Attempt to authenticate in RADIUS."""

        reply = self._try_radius(username, password)
        if reply is None:
            return None, None
        log = current_app.artemis_logger
        log.info("Received reply from radius, code=%s" % reply.code)
        if reply.code == AccessAccept:
            return True, self._calculate_role(reply)
        return False, None

    def _calculate_role(self, reply):
        log = current_app.artemis_logger
        role = self.default_role
        if self.role_mapping is None or self.role_attribute_code is None:
            log.debug("skip role mapping; default role is %s" % role)
            return role

        for rawCode in reply.keys():
            code = int(rawCode)
            value = reply[code][0]
            if code == self.role_attribute_code:
                log.debug("Found role mapping attr")
                for v in self.role_mapping.keys():
                    if isinstance(v, int):
                        cmp = int.from_bytes(value, byteorder='big', signed=False)
                        if int(cmp) == int(v):
                            role = self.role_mapping[v]
                    if isinstance(v, str):
                        cmp = str(value)
                        if cmp == v:
                            role = self.role_mapping[v]
        log.info("user role will map to %s" % role)
        return role

    def _create_radius_clients(self, servers):
        log = current_app.artemis_logger

        dictPath = os.path.dirname(__file__) + "/dictionary"

        def mk_client(x):
            try:
                c = Client(server=x["host"], authport=x["port"], secret=x["secret"].encode(), dict=Dictionary(dictPath))
            except KeyError as e:
                raise Exception(
                    "%s attribute is missing in one of the radius host entries. Please fix SECURITY_RADIUS_SERVERS:\n "
                    "%s" % (str(e), str(servers)))
            try:
                c.timeout = x["timeout"]
            except KeyError:
                pass
            try:
                c.retries = x["retries"]
            except KeyError:
                pass
            return c

        result = list(map(mk_client, servers))

        for s in result:
            log.info(" prepared radius connection to %s:%s, timeout=%s, retries=%s" % (
                s.server, s.authport, s.timeout, s.retries))

        return result

    def _try_radius(self, username, password):
        log = current_app.artemis_logger
        attempt = 1
        while attempt <= self.client_attempts:
            try:
                log.info("RADIUS authenticate user %s attempt %s server %s:%s (timeout=%s, retries=%s)" % (
                    username, attempt, self.current_client.server, self.current_client.authport,
                    self.current_client.timeout,
                    self.current_client.retries))
                r = self.current_client
                req = r.CreateAuthPacket(code=AccessRequest, User_Name=username)
                req["User-Password"] = req.PwCrypt(password)
                return r.SendPacket(req)
            except:
                log.error("No response from RADIUS, switching to next one")
                self.current_client = next(self.client_iterator)
            finally:
                attempt += 1
        log.error("Tried all servers - no luck")
        return None
