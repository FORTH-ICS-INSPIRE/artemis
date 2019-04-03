import json

from flask import Blueprint
from flask import current_app as app
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_security.decorators import login_required
from flask_security.decorators import roles_required
from flask_security.utils import hash_password
from flask_security.utils import verify_password
from webapp.core.actions import Comment_hijack
from webapp.core.actions import Hijacks_multiple_action
from webapp.core.actions import Learn_hijack_rule
from webapp.core.actions import rmq_hijack_action
from webapp.core.modules import Modules_state
from webapp.data.models import db
from webapp.data.models import User
from webapp.templates.forms import ApproveUserForm
from webapp.templates.forms import ChangePasswordForm
from webapp.templates.forms import DeleteUserForm
from webapp.templates.forms import MakeAdminForm
from webapp.templates.forms import RemoveAdminForm

actions = Blueprint("actions", __name__, template_folder="templates")


@actions.route("/hijacks/action/", methods=["POST"])
@roles_required("admin")
def hijack_action():
    data = json.loads(request.data.decode("utf-8"))

    try:
        action = data["action"]

        if action == "mitigate":
            obj = {
                "action": action,
                "routing_key": "mitigate",
                "exchange": "mitigation",
                "priority": 2,
                "payload": {"key": data["hijack_key"], "prefix": data["prefix"]},
            }

        elif action == "resolve":
            obj = {
                "action": action,
                "routing_key": "resolve",
                "exchange": "hijack-update",
                "priority": 2,
                "payload": {
                    "key": data["hijack_key"],
                    "prefix": data["prefix"],
                    "type": data["hijack_type"],
                    "hijack_as": int(data["hijack_as"]),
                },
            }

        elif action == "ignore":
            obj = {
                "action": action,
                "routing_key": "ignore",
                "exchange": "hijack-update",
                "priority": 2,
                "payload": {
                    "key": data["hijack_key"],
                    "prefix": data["prefix"],
                    "type": data["hijack_type"],
                    "hijack_as": int(data["hijack_as"]),
                },
            }

        elif action == "delete":
            obj = {
                "action": action,
                "routing_key": "delete",
                "exchange": "hijack-update",
                "priority": 2,
                "payload": {
                    "key": data["hijack_key"],
                    "prefix": data["prefix"],
                    "type": data["hijack_type"],
                    "hijack_as": int(data["hijack_as"]),
                },
            }

        elif action == "seen":
            obj = {
                "action": action,
                "routing_key": "seen",
                "exchange": "hijack-update",
                "priority": 2,
                "payload": {"key": data["hijack_key"], "state": data["state"]},
            }

        else:
            raise BaseException("unknown action requested")

        rmq_hijack_action(obj)

    except BaseException:
        app.artemis_logger.exception(
            "hijack_action - '{}' failed".format(data["action"])
        )
        return jsonify({"status": "fail"})
    return jsonify({"status": "success"})


@actions.route("/hijacks/learn_hijack_rule/", methods=["POST"])
@roles_required("admin")
def learn_hijack_rule():
    data_ = json.loads(request.data.decode("utf-8"))

    hijack_key = data_["hijack_key"]
    prefix = data_["prefix"]
    type_ = data_["type_"]
    hijack_as = int(data_["hijack_as"])
    action = data_["action"]

    _learn_hijack_rule = Learn_hijack_rule()
    response, success = _learn_hijack_rule.send(
        hijack_key, prefix, type_, hijack_as, action
    )

    if success:
        return jsonify({"status": "success", "response": response})
    return jsonify({"status": "fail", "response": response})


@actions.route("/submit_comment/", methods=["POST"])
@roles_required("admin")
def submit_new_comment():
    data_ = json.loads(request.data.decode("utf-8"))

    new_comment = data_["new_comment"]
    hijack_key = data_["hijack_key"]

    app.artemis_logger.debug(
        "hijack_key: {0} new_comment: {1}".format(hijack_key, new_comment)
    )

    comment_ = Comment_hijack()
    response, success = comment_.send(hijack_key, new_comment)

    if success:
        return jsonify({"status": "success", "data": new_comment, "response": response})
    return jsonify({"status": "fail", "data": new_comment, "response": response})


@actions.route("/approve_user", methods=["POST"])
@roles_required("admin")
def approve_user():
    form = ApproveUserForm(request.form)
    app.artemis_logger.debug("approve_user {}".format(form))

    if form.select_field.data:
        user = app.security.datastore.find_user(id=form.select_field.data)

        user_role = app.security.datastore.find_role("user")
        app.security.datastore.add_role_to_user(user, user_role)

        pending_role = app.security.datastore.find_role("pending")
        app.security.datastore.remove_role_from_user(user, pending_role)

        app.security.datastore.commit()

    return redirect(url_for("admin.user_management"))


@actions.route("/create_admin", methods=["POST"])
@roles_required("admin")
def create_admin():
    form = MakeAdminForm(request.form)
    app.artemis_logger.debug("create_admin {}".format(form))

    if form.select_field.data:
        user = app.security.datastore.find_user(id=form.select_field.data)

        admin_role = app.security.datastore.find_role("admin")
        app.security.datastore.add_role_to_user(user, admin_role)

        user_role = app.security.datastore.find_role("user")
        app.security.datastore.remove_role_from_user(user, user_role)

        app.security.datastore.commit()

    return redirect(url_for("admin.user_management"))


@actions.route("/remove_admin", methods=["POST"])
@roles_required("admin")
def remove_admin():
    form = RemoveAdminForm(request.form)
    app.artemis_logger.debug("remove_admin {}".format(form))

    if form.select_field.data:
        user = app.security.datastore.find_user(id=form.select_field.data)
        # Protect admin (user id == 1)
        if user.id == 1:
            return redirect(url_for("admin.user_management"))

        admin_role = app.security.datastore.find_role("admin")
        app.security.datastore.remove_role_from_user(user, admin_role)

        user_role = app.security.datastore.find_role("user")
        app.security.datastore.add_role_to_user(user, user_role)

        app.security.datastore.commit()

    return redirect(url_for("admin.user_management"))


@actions.route("/delete_user", methods=["POST"])
@roles_required("admin")
def delete_user():
    form = DeleteUserForm(request.form)
    app.artemis_logger.debug("delete user {}".format(form))

    if form.select_field.data:
        db.session.query(User).filter(User.id == form.select_field.data).delete()
        db.session.commit()

    return redirect(url_for("admin.user_management"))


@actions.route("/new/password", methods=["POST"])
@login_required
def set_new_password():
    form = ChangePasswordForm(request.form)
    user = app.security.datastore.get_user(session["user_id"])
    old_password = user.password
    _status = "empty"

    if form.validate_on_submit():
        if form.old_password.data:
            app.artemis_logger.debug(
                "verify: {}".format(
                    verify_password(form.old_password.data, old_password)
                )
            )
            if verify_password(form.old_password.data, old_password):
                app.artemis_logger.debug("password_match")
                user = User.query.filter_by(username=user.username).first()
                user.password = hash_password(form.password.data)
                db.session.commit()
                _status = "success"
            else:
                _status = "wrong_old_password"

    return render_template("new_password.htm", password_change=form, status=_status)


@actions.route("/password_change", methods=["GET"])
@login_required
def password_change():
    _password_change = ChangePasswordForm()
    _password_change.validate_on_submit()
    return render_template(
        "new_password.htm", password_change=_password_change, status=None
    )


@actions.route("/modify_state", methods=["POST"])
@roles_required("admin")
def monitor_state():
    try:
        modules_state = Modules_state()
        data = json.loads(request.data)
        if data["state"]:
            modules_state.call(data["name"], "start")
        else:
            modules_state.call(data["name"], "stop")
        return json.dumps({"success": True}), 200, {"ContentType": "application/json"}
    except Exception as e:
        return (
            json.dumps({"success": False, "error": str(e)}),
            500,
            {"ContentType": "application/json"},
        )


@actions.route("/multiple_hijack_actions", methods=["POST"])
@roles_required("admin")
def submit_hijacks_actions():
    data_ = json.loads(request.data.decode("utf-8"))
    hijack_keys = data_["hijack_keys"]
    action = data_["action"]

    multiple_action_ = Hijacks_multiple_action()
    success = multiple_action_.send(hijack_keys, action)

    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"})
