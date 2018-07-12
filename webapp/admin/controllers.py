from sqlalchemy import exc
from flask import Blueprint, render_template, flash
from flask import current_app, redirect, request, url_for
from flask_security.decorators import roles_required
from webapp.cache import cache
from webapp.data.models import User, db


admin = Blueprint('admin', __name__, template_folder='templates')


@admin.route('/')
@roles_required('admin')
def index():
    return render_template('admin_index.htm')


### EXAMPLE
@admin.route('/user/create', methods=['GET', 'POST'])
@roles_required('admin')
def create_author():
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
