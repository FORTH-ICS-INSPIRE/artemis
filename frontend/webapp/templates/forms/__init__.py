from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, \
    PasswordField, validators, TextField, SelectField, validators
from wtforms.fields.html5 import EmailField
from flask_security.forms import RegisterForm, LoginForm, Required
from webapp.data.models import db, User
import logging

log = logging.getLogger('webapp_logger')


class CheckboxMonitorForm(FlaskForm):
    monitor_switch = BooleanField('Monitor', default=False)


class CheckboxDetectorForm(FlaskForm):
    detection_switch = BooleanField('Detection', default=False)


class CheckboxMitigatorForm(FlaskForm):
    mitigation_switch = BooleanField('Mitigation', default=False)


class ExtendedRegisterForm(RegisterForm):
    username = StringField('Username', [Required()])
    email = EmailField(
        'Email', [
            validators.DataRequired(
                message='email is required '), validators.Email(
                message='invalid email address')])

    def validate(self):
        if db.session.query(User).filter(
                User.username == self.username.data.strip()).first():
            self.username.errors += ("Username already registered",)
            return False

        if db.session.query(User).filter(
                User.email == self.email.data.strip()).first():
            self.email.errors += ("Email already registered",)
            return False

        if not super(ExtendedRegisterForm, self).validate():
            return False

        return True


class ExtendedLoginForm(LoginForm):
    email = StringField('Username or Email Address', [Required()])
    password = PasswordField('Password', [Required()])


class ApproveUserForm(FlaskForm):
    select_field = SelectField(
        'Select pending user to approve:', [
            Required()], choices=[])


class MakeAdminForm(FlaskForm):
    select_field = SelectField(
        'Select user to promote to admin:', [
            Required()], choices=[])


class RemoveAdminForm(FlaskForm):
    select_field = SelectField(
        'Select user to demote from admin:', [
            Required()], choices=[])


class DeleteUserForm(FlaskForm):
    select_field = SelectField(
        'Select user to delete:', [
            Required()], choices=[])


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Old Password',
                                 [validators.DataRequired(),
                                  validators.Length(min=6, max=35)]
                                 )
    password = PasswordField('New Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords must match')
    ])
    confirm = PasswordField('Repeat Password')
    submit = SubmitField('Change Password')
