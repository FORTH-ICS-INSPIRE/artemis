# from webapp.core import app
import json

from flask import Blueprint
from flask import current_app as app
from flask import render_template
from flask import request
from flask_security.decorators import login_required
from flask_security.decorators import roles_accepted
from webapp.core.fetch_config import fetch_all_config_timestamps
from webapp.core.fetch_hijack import get_hijack_by_key
from webapp.core.modules import Modules_state

main = Blueprint("main", __name__, template_folder="templates")


@main.route("/bgpupdates/", methods=["GET"])
@login_required
@roles_accepted("admin", "user")
def display_monitors():
    app.config["configuration"].get_newest_config()
    prefixes_list = app.config["configuration"].get_prefixes_list()
    return render_template(
        "bgpupdates.htm", prefixes=prefixes_list, js_version=app.config["JS_VERSION"]
    )


@main.route("/hijacks/")
@login_required
@roles_accepted("admin", "user")
def display_hijacks():
    hijack_keys = request.args.get("hijack_keys")
    if hijack_keys is not None:
        if "," in hijack_keys:
            hijack_keys = hijack_keys.split(",")
        else:
            hijack_keys = [hijack_keys]
        return render_template("hijacks.htm", hijack_keys=hijack_keys)
    else:
        return render_template(
            "hijacks.htm", hijack_keys=None, js_version=app.config["JS_VERSION"]
        )


@main.route("/hijack", methods=["GET"])
@login_required
@roles_accepted("admin", "user")
def display_hijack():
    app.config["configuration"].get_newest_config()
    _key = request.args.get("key")
    mitigation_status_request = Modules_state()
    _mitigation_flag = False

    hijack_data = get_hijack_by_key(_key)

    if hijack_data is None:
        app.artemis_logger.debug("Hijack with id found: {}".format(_key))
        return render_template("404.htm")

    if mitigation_status_request.is_up_or_running("mitigation"):
        _mitigation_flag = True

    return render_template(
        "hijack.htm",
        data=json.dumps(hijack_data),
        mitigate=_mitigation_flag,
        js_version=app.config["JS_VERSION"],
    )


@main.route("/config_comparison", methods=["GET"])
@roles_accepted("admin", "user")
def config_comparison():
    # log info
    _configs = fetch_all_config_timestamps()
    return render_template(
        "config_comparison.htm",
        configs=list(reversed(_configs)),
        js_version=app.config["JS_VERSION"],
    )
