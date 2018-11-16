import os
import logging
from flask import Flask, g, render_template, request, current_app, jsonify, redirect, session
from flask_security import current_user
from flask_security.utils import hash_password
from flask_security.decorators import login_required, roles_accepted
from flask_babel import Babel
from flask_jwt_extended import JWTManager, create_access_token
from webapp.data.models import db
from webapp.utils.path import get_app_base_path
from webapp.configs.config import configure_app
from webapp.core.modules import Modules_state
from flask_security import user_registered
from webapp.core.proxy_api import get_proxy_api
from datetime import timedelta
from webapp.core.fetch_config import Configuration
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
    babel = Babel(app)
    app.jinja_env.add_extension('jinja2.ext.loopcontrols')
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    data_store = app.security.datastore
    jwt = JWTManager(app)

app.login_manager.session_protection = "strong"

from webapp.views.main.main_view import main
from webapp.views.admin.admin_view import admin
from webapp.views.actions.actions_view import actions

app.register_blueprint(main, url_prefix='/main')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(actions, url_prefix='/actions')


def load_user(payload):
    user = data_store.find_user(id=payload['identity'])
    return user


@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=15)


@app.before_first_request
def setup():
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', default='')
    app.config['configuration'] = Configuration()
    while not app.config['configuration'].get_newest_config():
        time.sleep(1)
        log.info('waiting for postgrest')

    try:
        app.config['VERSION'] = os.getenv('SYSTEM_VERSION')
    except BaseException:
        app.config['VERSION'] = 'Fail'
        log.debug('failed to get version')

    modules = Modules_state()

    try:
        log.debug('Starting Postgresql_db..')
        modules.call('postgresql_db', 'start')

        if not modules.is_up_or_running('postgresql_db'):
            log.error('Couldn\'t start postgresql_db.')
            exit(-1)
    except BaseException:
        log.exception('exception while starting postgresql_db')
        exit(-1)

    try:
        log.debug('Request status of all modules..')
        app.config['status'] = modules.get_response_all()
    except BaseException:
        log.exception('exception while retrieving status of modules..')
        exit(-1)

    log.debug("setting database for the first time")
    if not os.path.isfile(app.config['DB_FULL_PATH']):
        db.create_all()

        def create_roles(ctx):
            ctx.create_role(name='admin')
            ctx.commit()
            ctx.create_role(name='pending')
            ctx.commit()
            ctx.create_role(name='user')
            ctx.commit()
        create_roles(data_store)

        def create_user(ctx):

            try:
                email = os.getenv('USER_ROOT_EMAIL', '')
                username = os.getenv('USER_ROOT_USERNAME', 'admin')
                password = os.getenv('USER_ROOT_PASSWORD', 'admin')
                is_active = True
                if password is not None:
                    password = hash_password(password)

                user = ctx.create_user(username=username,
                                       email=email, password=password, active=is_active)
                ctx.commit()
                role = ctx.find_or_create_role('admin')

                ctx.add_role_to_user(user, role)
                ctx.commit()
            except BaseException:
                log.exception("exception")

        create_user(data_store)


@app.errorhandler(404)
def page_not_found(error):
    current_app.logger.error('Page not found: %s', (request.path, error))
    log.debug('{}'.format(error))
    return render_template('404.htm')


@app.errorhandler(500)
def internal_server_error(error):
    current_app.logger.error('Server Error: %s', (error))
    return render_template('500.htm')


@app.errorhandler(Exception)
def unhandled_exception(error):
    current_app.logger.error('Unhandled Exception: %s', (error))
    log.error('Unhandled Exception', exc_info=True)
    return render_template('500.htm')


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


@user_registered.connect_via(app)
def on_user_registered(app, user, confirm_token):
    default_role = data_store.find_role("pending")
    data_store.add_role_to_user(user, default_role)
    db.session.commit()


@app.route('/jwt/auth', methods=['GET'])
def jwt_auth():
    user = None
    # if user is not logged in check parameters
    if not current_user.is_authenticated:
        username = request.values.get('username')
        password = request.values.get('password')
        # if user and pass does not correspond to user return unauthorized
        user = data_store.find_user(username=username, password=password)
        if user is None:
            return current_app.login_manager.unauthorized()
    else:
        user = current_user
    # Create the tokens we will be sending back to the user
    access_token = create_access_token(identity=user)
    # Set the JWT cookies in the response
    resp = jsonify({'access_token': access_token})
    return resp, 200


@jwt.user_identity_loader
def user_identity_lookup(identity):
    return identity.username


@jwt.user_claims_loader
def add_claims_to_access_token(identity):
    role = identity.roles[0].name
    return {
        'x-hasura-allowed-roles': [role],
        'x-hasura-default-role': role,
        'x-hasura-user-id': str(identity.id)
    }


@app.route('/', methods=['GET', 'POST'])
def index():
    if not current_user.is_authenticated:
        return redirect("/login")
    elif current_user.has_role(data_store.find_role("pending")):
        return redirect("/pending")
    else:
        return redirect("/overview")


@app.route('/pending', methods=['GET', 'POST'])
@login_required
@roles_accepted('pending')
def pending():
    return render_template('pending.htm')


@app.route('/overview', methods=['GET', 'POST'])
@login_required
@roles_accepted('admin', 'user')
def overview():
    log.debug("url: /")
    app.config['configuration'].get_newest_config()
    newest_config = app.config['configuration'].get_raw_config()
    return render_template('index.htm',
                           config=newest_config,
                           config_timestamp=app.config['configuration'].get_config_last_modified())


@app.login_manager.unauthorized_handler
def unauth_handler():
    return render_template('401.htm')


@login_required
@roles_accepted('admin', 'user')
@app.route('/proxy_api', methods=['POST'])
def proxy_api():
    log.debug("/proxy_api")
    parameters = request.values.get('parameters')
    action = request.values.get('action')
    return jsonify(get_proxy_api(action, parameters))
