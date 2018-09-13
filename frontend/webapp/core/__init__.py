import os
import logging
from flask import abort, Flask, g, render_template, request, current_app
from flask_bootstrap import Bootstrap
from flask_security import current_user
from flask_security.utils import hash_password, verify_password
from flask_security.decorators import login_required
from flask_babel import Babel
from flask_jwt import JWT, jwt_required
from webapp.data.models import db
from webapp.utils.path import get_app_base_path
from webapp.configs.config import configure_app
from webapp.core.modules import Modules_status 
from webapp.utils import log
import time


app = Flask(__name__,
            instance_path=get_app_base_path(),
            instance_relative_config=True,
            template_folder='../templates', 
            static_url_path='',
            static_folder='../static')

with app.app_context():
    configure_app(app)
    db.init_app(app)
    Bootstrap(app)
    babel = Babel(app)
    app.jinja_env.add_extension('jinja2.ext.loopcontrols')
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    data_store = app.security.datastore

from webapp.main.controllers import main
from webapp.admin.controllers import admin
from webapp.templates.forms import CheckboxForm, ConfigForm

app.register_blueprint(main, url_prefix='/main')
app.register_blueprint(admin, url_prefix='/admin')

def authenticate(username, password):
    user = data_store.find_user(email=username)
    if user and username == user.email and verify_password(password, user.password):
        return user
    return None

def load_user(payload):
    user = data_store.find_user(id=payload['identity'])
    return user

jwt = JWT(app, authenticate, load_user)

@jwt_required()
def auth_func(**kw):
    pass

@app.before_first_request
def setupDatabase():

    if app.config['ENV'] in ['testing', 'dev']:
        if os.path.exists(app.config['SQLALCHEMY_DATABASE_URI'][10:]):
            os.remove(app.config['SQLALCHEMY_DATABASE_URI'][10:])

    if not os.path.exists(app.config['SQLALCHEMY_DATABASE_URI'][10:]):
        db.create_all()

        def create_roles(ctx):
            ctx.create_role(name='admin')
            ctx.commit()
        create_roles(data_store)

        def create_users(ctx):
            users = [('a', 'a', 'a', ['admin'], True),
                    ('u', 'u', 'u', [], True)]
            for user in users:
                email = user[0]
                username = user[1]
                password = user[2]
                is_active = user[4]
                if password is not None:
                    password = hash_password(password)
                roles = [ctx.find_or_create_role(rn) for rn in user[3]]
                ctx.commit()
                user = ctx.create_user(
                    email=email, password=password, active=is_active)
                ctx.commit()
                for role in roles:
                    ctx.add_role_to_user(user, role)
                ctx.commit()
        create_users(data_store)



@app.errorhandler(404)
def page_not_found(error):
    current_app.logger.error('Page not found: %s', (request.path, error))
    return '{}'.format(error)
    # return render_template('404.htm'), 404


@app.errorhandler(500)
def internal_server_error(error):
    current_app.logger.error('Server Error: %s', (error))
    return '{}'.format(error)
    # return render_template('500.htm'), 500


@app.errorhandler(Exception)
def unhandled_exception(error):
    current_app.logger.error('Unhandled Exception: %s', (error))
    log.error('Unhandled Exception', exc_info=True)
    return '{}'.format(error)
    # return render_template('500.htm'), 500


@app.context_processor
def inject_user():
    return dict(user=current_user)

@app.context_processor
def inject_version():
    return dict(version=app.config['VERSION'])

@babel.timezoneselector
def get_timezone():
    user = g.get('user', None)
    if user is not None:
        return user.timezone
    return 'UTC'


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    status_request = Modules_status()
    status_request.call('all', 'status')
    app.config['status'] = status_request.get_response_all()
    return render_template('index.htm', modules = app.config['status'])


