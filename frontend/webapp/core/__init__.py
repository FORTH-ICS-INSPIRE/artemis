import os
from flask import Flask, g, render_template, request, jsonify, redirect, session
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
from webapp.core.proxy_api import proxy_api_post, proxy_api_downloadTable
from datetime import timedelta
from webapp.core.fetch_config import Configuration
from webapp.views.main.main_view import main
from webapp.views.admin.admin_view import admin
from webapp.views.actions.actions_view import actions
import time
import logging

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
    werk_log = logging.getLogger('werkzeug')
    werk_log.setLevel(logging.ERROR)
    data_store = app.security.datastore
    jwt = JWTManager(app)

app.login_manager.session_protection = "strong"
app.register_blueprint(main, url_prefix='/main')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(actions, url_prefix='/actions')


def load_user(payload):
    user = data_store.find_user(id=payload['identity'])
    return user


@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=60)


@app.before_first_request
def setup():
    app.config['configuration'] = Configuration()
    while not app.config['configuration'].get_newest_config():
        time.sleep(1)
        app.artemis_logger.info('waiting for postgrest')

    try:
        app.config['VERSION'] = os.getenv('SYSTEM_VERSION')
    except BaseException:
        app.config['VERSION'] = 'Fail'
        app.artemis_logger.debug('failed to get version')

    modules = Modules_state()

    try:
        app.artemis_logger.debug('Starting Database..')
        modules.call('database', 'start')

        if not modules.is_up_or_running('database'):
            app.artemis_logger.error('Couldn\'t start Database.')
            exit(-1)
    except BaseException:
        app.artemis_logger.exception('exception while starting Database')
        exit(-1)

    try:
        app.artemis_logger.debug('Request status of all modules..')
        app.config['status'] = modules.get_response_all()
    except BaseException:
        app.artemis_logger.exception(
            'exception while retrieving status of modules..')
        exit(-1)

    app.artemis_logger.debug("setting database for the first time")
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
                app.artemis_logger.exception("exception")

        create_user(data_store)


@app.errorhandler(404)
def page_not_found(error):
    app.artemis_logger.debug('Page Not Found Error: {}'.format(error))
    return render_template('404.htm')


@app.errorhandler(500)
def internal_server_error(error):
    app.artemis_logger.error('Server Error: {}'.format(error))
    return render_template('500.htm')


@app.errorhandler(Exception)
def unhandled_exception(error):
    app.artemis_logger.error('Unhandled Exception: {}'.format(error))
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
            return app.login_manager.unauthorized()
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
    app.artemis_logger.debug("url: /")
    app.config['configuration'].get_newest_config()
    newest_config = app.config['configuration'].get_raw_config()
    return render_template('index.htm',
                           config=newest_config,
                           config_timestamp=app.config['configuration'].get_config_last_modified(
                           ),
                           js_version=app.config['JS_VERSION'])


@app.login_manager.unauthorized_handler
def unauth_handler():
    return render_template('401.htm')


@login_required
@roles_accepted('admin', 'user')
@app.route('/proxy_api', methods=['GET', 'POST'])
def proxy_api():
    if request.method == 'POST':
        parameters = request.values.get('parameters')
        action = request.values.get('action')
        return jsonify(proxy_api_post(action, parameters))

    download_table = request.args.get('download_table')
    parameters = request.args.get('parameters')
    action = request.args.get('action')

    if download_table == 'true':
        return proxy_api_downloadTable(action, parameters)

    return jsonify(proxy_api_post(action, parameters))
