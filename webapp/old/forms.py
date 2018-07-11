from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, \
    PasswordField, validators, TextField
from wtforms.widgets import TextArea


class CheckboxForm(FlaskForm):
    monitor = BooleanField('Monitor', default=False)
    detector = BooleanField('Detector', default=False)
    mitigator = BooleanField('Mitigator', default=False)
    submit = SubmitField('Submit')


class ConfigForm(FlaskForm):
    config = StringField(widget=TextArea())


class LoginForm(FlaskForm):
    username = TextField(
        'Username', [validators.Required(), validators.Length(min=4, max=25)])
    password = PasswordField(
        'Password', [validators.Required(), validators.Length(min=4, max=200)])
    remember_me = BooleanField('Remember Me')
    login = SubmitField('Login')

    def __repr__(self):
        return '<LoginForm> usr: {}, pass: {}, login: {}'.format(
            self.username.data, self.password.data, self.login.data)
