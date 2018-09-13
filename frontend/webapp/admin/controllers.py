from sqlalchemy import exc
from flask import Blueprint, render_template, flash
from flask import current_app, redirect, request, url_for
from flask_security.decorators import roles_required
from webapp.data.models import User, db
from webapp.templates.forms import CheckboxForm, ConfigForm
from webapp.core import app
from webapp.core.modules import Modules_status 
import yaml

admin = Blueprint('admin', __name__, template_folder='templates')


@admin.route('/system', methods=['GET', 'POST'])
@roles_required('admin')
def index():
    form = CheckboxForm()
    config_form = ConfigForm()
    config_form.config.data = yaml.dump(app.config['configuration'].get_raw_config())

    status_request = Modules_status()
    status_request.call('all', 'status')
    app.config['status'] = status_request.get_response_all()

    if form.validate_on_submit():
        if form.monitor.data:
            status_request.call('monitor', 'start')
        else:
            status_request.call('monitor', 'stop')
        if form.detector.data:
            status_request.call('detection', 'start')
        else:
            status_request.call('detection', 'stop')
        if form.mitigator.data:
            status_request.call('mitigation', 'start')
        else:
            status_request.call('mitigation', 'stop')
    else:
        if app.config['status']['monitor'] == 'up':
            form.monitor.data = True
        else:
            form.monitor.data = False
        if app.config['status']['detection'] == 'up':
            form.detector.data = True
        else:
            form.detector.data = False
        if app.config['status']['mitigation'] == 'up':
            form.mitigator.data = True
        else:
            form.mitigator.data = False

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
