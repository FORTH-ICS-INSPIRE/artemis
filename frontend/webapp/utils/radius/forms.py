"""Provides Flask-Security login forms for usage with RADIUS auth backend."""
from flask import current_app
from flask import request
from flask_security.confirmable import requires_confirmation
from flask_security.forms import Form
from flask_security.forms import get_form_field_label
from flask_security.forms import NextFormMixin
from flask_security.utils import config_value
from flask_security.utils import get_message
from flask_security.utils import verify_and_update_password
from werkzeug.local import LocalProxy
from wtforms import BooleanField
from wtforms import PasswordField
from wtforms import StringField
from wtforms import SubmitField

_datastore = LocalProxy(lambda: current_app.extensions["security"].datastore)


class RADIUSLoginForm(Form, NextFormMixin):
    """Login form for RADIUS users."""

    email = StringField("User ID")
    password = PasswordField(get_form_field_label("password"))
    remember = BooleanField(get_form_field_label("remember_me"))
    submit = SubmitField(get_form_field_label("login"))

    def __init__(self, *args, **kwargs):
        """Init new RADIUS login form."""
        super(RADIUSLoginForm, self).__init__(*args, **kwargs)
        self._args = args
        self._kwargs = kwargs
        if not self.next.data:
            self.next.data = request.args.get("next", "")
        self.remember.default = config_value("DEFAULT_REMEMBER_ME")

    def validate(self):
        """Validate."""

        log = current_app.artemis_logger

        log.info("RADIUS authenticate() using username %s" % self.email.data)

        if not super(RADIUSLoginForm, self).validate():
            log.warn("super() validate was false!")
            return False

        if self.email.data.strip() == "":
            self.email.errors.append(get_message("USERID_NOT_PROVIDED")[0])
            log.warn("userid was not provided")
            return False

        if self.password.data.strip() == "":
            log.warn("password was not provided")
            self.password.errors.append(get_message("PASSWORD_NOT_PROVIDED")[0])
            return False

        try:
            admin_user = _datastore.get_user(1)
            if self.email.data == admin_user.username:
                log.info("Login using Super-user login")
                return self._try_local_auth()

            auth_result, role = _datastore.authenticate(
                self.email.data, self.password.data
            )
            if auth_result is None:
                self.password.errors.append("No response from RADIUS")
                log.info("RADIUS authenticate() returned None")
                return False
            if not auth_result:
                self.password.errors.append(get_message("INVALID_PASSWORD")[0])
                log.info("RADIUS authenticate() returned False")
                return False
            log.info("RADIUS authenticate() returned True. Assigning role %s" % role)
            username = self.email.data
            self.user = _datastore.find_user(username=username)
            if self.user:
                self.user.password = None
                self.user.email = username
            else:
                self.user = _datastore.create_user(
                    username=username, email=username, password=None, active=True
                )
            self._set_role(self.user, _datastore.find_role(role))
            _datastore.commit()
        except Exception:
            self.password.errors.append(
                "Internal error. Contact developer and/or check the logs."
            )
            log.exception("Unexpected error while handling RADIUS form")
            return False

        return True

    # because the user manipulation is broken i.e. it can lead to multiple entries in roles_users table (perhaps lack of
    # primary key in the table definition?) so until it's fixed the role manipulation is done via low level sqls
    def _set_role(self, user, role):
        _datastore.db.session.execute(
            """delete from roles_users where user_id=:user_id""", {"user_id": user.id}
        )
        _datastore.db.session.execute(
            """insert into roles_users (user_id,role_id) values (:user_id, :role_id)""",
            {"user_id": user.id, "role_id": role.id},
        )

    def _try_local_auth(self):
        self.user = _datastore.find_user(username=self.email.data)

        if not self.user:
            self.email.errors.append(get_message("USER_DOES_NOT_EXIST")[0])
            return False
        if not self.user.password:
            self.password.errors.append(get_message("PASSWORD_NOT_SET")[0])
            return False
        if not verify_and_update_password(self.password.data, self.user):
            self.password.errors.append(get_message("INVALID_PASSWORD")[0])
            return False
        if requires_confirmation(self.user):
            self.email.errors.append(get_message("CONFIRMATION_REQUIRED")[0])
            return False
        if not self.user.is_active:
            self.email.errors.append(get_message("DISABLED_ACCOUNT")[0])
            return False

        return True
