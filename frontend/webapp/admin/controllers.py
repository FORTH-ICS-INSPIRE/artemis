from sqlalchemy import exc
from flask import Blueprint, render_template, flash
from flask import current_app, redirect, request, url_for
from flask_security.decorators import roles_required
from webapp.cache import cache
from webapp.data.models import User, db
from webapp.templates.forms import CheckboxForm, ConfigForm
from webapp.core import app
import yaml

admin = Blueprint('admin', __name__, template_folder='templates')


@admin.route('/system', methods=['GET'])
@roles_required('admin')
def index():
    form = CheckboxForm()
    config_form = ConfigForm()

    config_form.config.data = yaml.dump(app.config['CONFIG'].get_raw_config())

    if form.validate_on_submit():
        if form.monitor.data:
            app.config['monitor'].start()
        else:
            app.config['monitor'].stop()
        if form.detector.data:
            app.config['detector'].start()
        else:
            app.config['detector'].stop()
        if form.mitigator.data:
            app.config['mitigator'].start()
        else:
            app.config['mitigator'].stop()
    else:
        form.monitor.data = app.config['monitor'].flag
        form.detector.data = app.config['detector'].flag
        form.mitigator.data = app.config['mitigator'].flag
    return render_template('system.htm', form=form, config=config_form)


### EXAMPLE
@admin.route('/user/create', methods=['GET'])
@roles_required('admin')
def create_user():
    form = CreateUserForm(request.form)
    if request.method == 'POST' and form.validate():
        names = form.names.data
        current_app.logger.info('Adding a new user %s.', (names))
        user = User(...)

        try:
            db.session.add(user)
            db.session.commit()
            cache.clear()
            flash('User successfully created.')
        except exc.SQLAlchemyError as e:
            flash('User was not created.')
            current_app.logger.error(e)

            return redirect(url_for('admin.create_user'))

        return redirect(url_for('main.display_users'))

    return render_template('create_user.htm', form=form)
