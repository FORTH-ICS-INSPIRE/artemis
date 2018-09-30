from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, \
    PasswordField, validators, TextField, SelectField
from wtforms.fields.html5 import EmailField
from flask_security.forms import RegisterForm, LoginForm, Required
import logging

log = logging.getLogger('artemis_logger')

class CheckboxForm(FlaskForm):
    monitor = BooleanField('Monitor', default=False)
    detector = BooleanField('Detector', default=False)
    mitigator = BooleanField('Mitigator', default=False)


class ExtendedRegisterForm(RegisterForm):
    username = StringField('Username', [Required()])
    email = EmailField('Email', [validators.DataRequired(message='email is required '), validators.Email(message='invalid email address')])

class ExtendedLoginForm(LoginForm):
    email = StringField('Username or Email Address', [Required()])
    password = PasswordField('Password', [Required()])

class ApproveUserForm(FlaskForm):
    user_to_approve = SelectField('Select pending user to approve:', [Required()], choices=[])

class MakeAdminForm(FlaskForm):
    user_to_make_admin = SelectField('Select user to promote to admin:', [Required()], choices=[])

class DeleteUserForm(FlaskForm):
    user_to_delete = SelectField('Select user to delete:', [Required()], choices=[])