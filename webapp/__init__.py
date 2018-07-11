from flask import abort, Flask, g, render_template, request, current_app
from flask_bootstrap import Bootstrap
from flask_security import current_user
from flask_security.utils import encrypt_password
from flask_security.decorators import login_required
from flask_babel import Babel
from webapp.data.models import db
from webapp.utils import get_instance_folder_path
from webapp.config import configure_app
from webapp.cache import cache
import time

app = Flask(__name__,
            instance_path=get_instance_folder_path(),
            instance_relative_config=True,
            template_folder='templates')

configure_app(app)
cache.init_app(app)
db.init_app(app)
Bootstrap(app)
babel = Babel(app)
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

from webapp.main.controllers import main
from webapp.admin.controllers import admin
from webapp.templates.forms import CheckboxForm, ConfigForm

@app.before_first_request
def setupDatabase():
    data_store = app.security.datastore
    db.drop_all()
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
                password = encrypt_password(password)
            roles = [ctx.find_or_create_role(rn) for rn in user[3]]
            ctx.commit()
            user = ctx.create_user(
                email=email, password=password, active=is_active)
            ctx.commit()
            for role in roles:
                ctx.add_role_to_user(user, role)
            ctx.commit()
    create_users(data_store)

    def add_monitors():
        from webapp.data.models import Monitor
        msg = {'prefix':'192.168.0.0/24', 'service':'custom', 'type':'W', 'timestamp':time.time()}
        monitor = Monitor(msg)
        db.session.add(monitor)
        db.session.commit()
    add_monitors()


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
    return '{}'.format(error)
    # return render_template('500.htm'), 500


@app.context_processor
def inject_user():
    return dict(user=current_user)


@babel.timezoneselector
def get_timezone():
    user = g.get('user', None)
    if user is not None:
        return user.timezone
    return 'UTC'


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    form = CheckboxForm()
    config_form = ConfigForm()

    with open('configs/config', 'r') as f:
        config_form.config.data = f.read()

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

    return render_template('index.htm', config=config_form, form=form)

app.register_blueprint(main, url_prefix='/main')
app.register_blueprint(admin, url_prefix='/admin')
