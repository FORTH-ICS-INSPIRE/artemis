from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, \
    PasswordField, validators, TextField
from wtforms.widgets import TextArea


class CheckboxForm(FlaskForm):
    monitor = BooleanField('Monitor', default=False)
    detector = BooleanField('Detector', default=False)
    mitigator = BooleanField('Mitigator', default=False)
    submit = SubmitField('Save')
