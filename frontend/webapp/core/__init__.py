import os
import logging
from flask import abort, Flask, g, render_template, request, current_app, jsonify, redirect
from flask_bootstrap import Bootstrap
from flask_security import current_user, login_user
from flask_security.utils import hash_password, verify_password
from flask_security.decorators import login_required, roles_accepted
from flask_babel import Babel
from webapp.data.models import db, User
from webapp.utils.path import get_app_base_path
from webapp.configs.config import configure_app
from webapp.core.modules import Modules_status 
from webapp.templates.forms import ExtendedRegisterForm, ExtendedLoginForm
from flask_security import user_registered
from webapp.core.proxy_api import get_proxy_api
import time

log = logging.getLogger('webapp_logger')


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

app.register_blueprint(main, url_prefix='/main')
app.register_blueprint(admin, url_prefix='/admin')


def load_user(payload):
    log.debug("payload: {0}".format(payload))
    user = data_store.find_user(id=payload['identity'])
    return user


@app.before_first_request
def setupDatabase():
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
            except:
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

@app.context_processor
def inject_API_url():
    return dict(API_url=app.config['CLIENT_API_URL'])

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
    status_request = Modules_status()
    status_request.call('all', 'status')
    modules_formmated = status_request.get_response_formmated_all()
    app.config['configuration'].get_newest_config()
    newest_config = app.config['configuration'].get_raw_config()
    db_stats = app.config['db_stats'].get_all_formatted_list()
    return render_template('index.htm', 
        modules = modules_formmated, 
        config = newest_config, 
        db_stats = db_stats,
        config_timestamp = app.config['configuration'].get_config_last_modified())

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
