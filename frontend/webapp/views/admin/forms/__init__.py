from flask_wtf import FlaskForm
from wtforms import BooleanField
from wtforms import SubmitField


class CheckboxForm(FlaskForm):
    monitor = BooleanField("Monitor", default=False)
    detector = BooleanField("Detector", default=False)
    mitigator = BooleanField("Mitigator", default=False)
    submit = SubmitField("Save")
