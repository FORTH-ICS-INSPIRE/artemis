import logging
import os
import time
from datetime import timedelta

import ujson as json
from flask import abort
from flask import Flask
from flask import g
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask_babel import Babel
from flask_jwt_extended import create_access_token
from flask_jwt_extended import JWTManager
from flask_security import current_user
from flask_security import user_registered
from flask_security.decorators import login_required
from flask_security.decorators import roles_accepted
from flask_security.utils import hash_password
from flask_security.utils import verify_password
from flask_talisman import Talisman
from webapp.configs.config import configure_app
from webapp.core.fetch_config import Configuration
from webapp.core.modules import Modules_state
from webapp.core.proxy_api import proxy_api_downloadTable
from webapp.core.proxy_api import proxy_api_post
from webapp.data.models import db
from webapp.render.views.actions_view import actions
from webapp.render.views.admin_view import admin
from webapp.render.views.errors_view import errors
from webapp.render.views.main_view import main
from webapp.utils.path import get_app_base_path

app = Flask(
    __name__,
    instance_path=get_app_base_path(),
    instance_relative_config=True,
    template_folder="../render/templates",
    static_url_path="",
    static_folder="../render/static",
)

# Content Security Policy
csp = {
    "default-src": "'self'",
    "script-src": "'self'",
    "connect-src": ["'self'", "stat.ripe.net"],
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "stackpath.bootstrapcdn.com",
        "cdn.datatables.net",
    ],
    "frame-ancestors": "'none'",
    "img-src": "'self' data:",
    "object-src": "'none'",
}

with app.app_context():
    configure_app(app)
    db.init_app(app)
    babel = Babel(app)
    app.jinja_env.add_extension("jinja2.ext.loopcontrols")
    werk_log = logging.getLogger("werkzeug")
    werk_log.setLevel(logging.ERROR)
    data_store = app.security.datastore
    jwt = JWTManager(app)
    talisman = Talisman(
        app,
        force_https=False,
        content_security_policy=csp,
        content_security_policy_nonce_in=["script-src"],
    )

app.login_manager.session_protection = "strong"
app.register_blueprint(main, url_prefix="/main")
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(actions, url_prefix="/actions")
app.register_blueprint(errors, url_prefix="/errors")


def load_user(payload):
    user = data_store.find_user(id=payload["identity"])
    return user


@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=60)


@app.before_first_request
def setup():
    app.config["configuration"] = Configuration()
    while not app.config["configuration"].get_newest_config():
        time.sleep(1)
        app.artemis_logger.info("waiting for postgrest")

    try:
        app.config["VERSION"] = "{}@{}".format(
            os.getenv("SYSTEM_VERSION"), os.getenv("REVISION", "HEAD")
        )
    except BaseException:
        app.config["VERSION"] = "Fail"
        app.artemis_logger.debug("failed to get version")

    modules = Modules_state()

    try:
        app.artemis_logger.debug("Starting Database..")

        if not modules.is_any_up_or_running("database"):
            app.artemis_logger.error("Couldn't start Database.")
            exit(-1)
    except BaseException:
        app.artemis_logger.exception("exception while starting Database")
        exit(-1)

    try:
        app.artemis_logger.debug("Request status of all modules..")
        app.config["status"] = modules.get_response_all()
    except BaseException:
        app.artemis_logger.exception("exception while retrieving status of modules..")
        exit(-1)

    if not os.path.isfile(app.config["DB_FULL_PATH"]):
        app.artemis_logger.debug("setting database for the first time")
        db.create_all()

        def create_roles(ctx):
            ctx.create_role(name="admin")
            ctx.commit()
            ctx.create_role(name="pending")
            ctx.commit()
            ctx.create_role(name="user")
            ctx.commit()

        create_roles(data_store)

        def create_user(ctx):

            try:
                email = os.getenv("USER_ROOT_EMAIL", "")
                username = os.getenv("USER_ROOT_USERNAME", "admin")
                password = os.getenv("USER_ROOT_PASSWORD", "admin")
                is_active = True
                if password:
                    password = hash_password(password)

                user = ctx.create_user(
                    username=username, email=email, password=password, active=is_active
                )
                ctx.commit()
                role = ctx.find_or_create_role("admin")

                ctx.add_role_to_user(user, role)
                ctx.commit()
            except BaseException:
                app.artemis_logger.exception("exception")

        create_user(data_store)

    app.extensions["security"]._unauthorized_callback = lambda: abort(400)


@app.errorhandler(400)
def bad_request(error):
    app.artemis_logger.info("Page Not Found Error: {}".format(error))
    return redirect("/errors/400")


@app.errorhandler(404)
def page_not_found(error):
    app.artemis_logger.info("Page Not Found Error: {}".format(error))
    return redirect("/errors/400")


@app.errorhandler(500)
def internal_server_error(error):
    app.artemis_logger.error("Server Error: {}".format(error))
    return redirect("/errors/500")


@app.errorhandler(Exception)
def unhandled_exception(error):
    app.artemis_logger.exception("Unhandled Exception: {}".format(error))
    return redirect("/errors/500")


@app.login_manager.unauthorized_handler
def unauth_handler():
    return redirect("/login")


@app.context_processor
def inject_user():
    return dict(user=current_user)


@app.context_processor
def inject_version():
    return dict(version=app.config["VERSION"])


@babel.timezoneselector
def get_timezone():
    user = g.get("user", None)
    if user is not None:
        return user.timezone
    return "UTC"


@user_registered.connect_via(app)
def on_user_registered(app, user, confirm_token):
    user_ = data_store.find_role("user")
    data_store.remove_role_from_user(user, user_)

    pending_ = data_store.find_role("pending")
    data_store.add_role_to_user(user, pending_)
    db.session.commit()


@app.route("/jwt/auth", methods=["GET", "POST"])
def jwt_auth():
    user = None

    # if user is not logged in check parameters
    if not current_user.is_authenticated:
        data = request.get_json()
        if not data:
            resp = jsonify({"error": "wrong credentials"})
            return resp, 400
        username = data["username"]
        password = data["password"]
        app.artemis_logger.info(username)
        # if user and pass does not correspond to user return unauthorized
        user = data_store.find_user(username=username)

        if not user or not verify_password(password, user.password):
            resp = jsonify({"error": "wrong credentials"})
            return resp, 400
    else:
        user = current_user
    # Create the tokens we will be sending back to the user
    access_token = create_access_token(identity=user)
    # Set the JWT cookies in the response
    resp = jsonify({"access_token": access_token})
    return resp, 200


@jwt.user_identity_loader
def user_identity_lookup(identity):
    return identity.username


@jwt.user_claims_loader
def add_claims_to_access_token(identity):
    role = identity.roles[0].name
    return {
        "x-hasura-allowed-roles": [role],
        "x-hasura-default-role": role,
        "x-hasura-user-id": str(identity.id),
    }


@app.route("/", methods=["GET", "POST"])
def index():
    if not current_user.is_authenticated:
        return redirect("/login")
    if current_user.has_role(data_store.find_role("pending")):
        return redirect("/pending")
    return redirect("/overview")


@app.route("/pending", methods=["GET", "POST"])
@login_required
@roles_accepted("pending")
def pending():
    return render_template("/main/pending.htm")


@app.route("/overview", methods=["GET", "POST"])
@login_required
@roles_accepted("admin", "user")
def overview():
    app.artemis_logger.debug("url: /")
    return render_template("/main/overview.htm", js_version=app.config["JS_VERSION"])


@app.route("/proxy_api", methods=["GET", "POST"])
@login_required
@roles_accepted("admin", "user")
def proxy_api():
    if request.method == "POST":
        data = json.loads(request.data.decode("utf-8"))
        parameters = data["parameters"]
        action = data["action"]
        return jsonify(proxy_api_post(action, parameters))

    download_table = request.args.get("download_table")
    parameters = request.args.get("parameters")
    action = request.args.get("action")

    if download_table == "true":
        return proxy_api_downloadTable(action, parameters)

    return jsonify(proxy_api_post(action, parameters))
