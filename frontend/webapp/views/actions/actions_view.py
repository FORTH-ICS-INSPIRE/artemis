from flask import Blueprint, render_template, session
from flask import redirect, request, jsonify
from flask_security.decorators import roles_required, login_required
from flask_security.utils import hash_password, verify_password
from webapp.data.models import db, User
from webapp.templates.forms import ApproveUserForm, MakeAdminForm, DeleteUserForm, ChangePasswordForm
from webapp.core.actions import Resolve_hijack, Mitigate_hijack, Ignore_hijack, Comment_hijack
from webapp.core import app
import logging

log = logging.getLogger('webapp_logger')

actions = Blueprint('actions', __name__, template_folder='templates')


@actions.route('/hijacks/resolve/', methods=['POST'])
@roles_required('admin')
def resolve_hijack():
    # log info
    hijack_key = request.values.get('hijack_key')
    prefix = request.values.get('prefix')
    type_ = request.values.get('type_')
    hijack_as = request.values.get('hijack_as')
    log.debug('url: /hijacks/resolve/{}'.format(hijack_key))
    resolve_hijack_ = Resolve_hijack(hijack_key)
    resolve_hijack_.resolve()
    return jsonify({'status': 'success'})


@actions.route('/hijacks/mitigate/', methods=['POST'])
@roles_required('admin')
def mitigate_hijack():
    # log info
    hijack_key = request.values.get('hijack_key')
    prefix = request.values.get('prefix')

    try:
        _mitigate_hijack = Mitigate_hijack(hijack_key, prefix)
        _mitigate_hijack.mitigate()
    except BaseException:
        log.debug("mitigate_hijack failed")

    return jsonify({'status': 'success'})


@actions.route('/hijacks/ignore/', methods=['POST'])
@roles_required('admin')
def ignore_hijack():
    # log info
    hijack_key = request.values.get('hijack_key')
    prefix = request.values.get('prefix')
    type_ = request.values.get('type_')
    hijack_as = request.values.get('hijack_as')

    try:
        _ignore_hijack = Ignore_hijack(hijack_key, prefix, type_, hijack_as)
        _ignore_hijack.ignore()

    except BaseException:
        log.debug("ignore_hijack failed")

    return jsonify({'status': 'success'})


@actions.route('/submit_comment/', methods=['POST'])
@roles_required('admin')
def submit_new_comment():
    # log info
    new_comment = request.values.get('new_comment')
    hijack_key = request.values.get('hijack_key')
    log.debug(
        "hijack_key: {0} new_comment: {1}".format(
            hijack_key,
            new_comment))

    comment_ = Comment_hijack()
    response, success = comment_.send(hijack_key, new_comment)

    if success:
        return jsonify(
            {'status': 'success', 'data': new_comment, 'response': response})
    else:
        return jsonify(
            {'status': 'fail', 'data': new_comment, 'response': response})


@actions.route('/approve_user', methods=['POST'])
@roles_required('admin')
def approve_user():
    # log info
    form = ApproveUserForm(request.form)
    log.debug("approve_user {}".format(form))

    if form.user_to_approve.data is not None:
        user = app.security.datastore.find_user(id=form.user_to_approve.data)

        user_role = app.security.datastore.find_role("user")
        app.security.datastore.add_role_to_user(user, user_role)

        pending_role = app.security.datastore.find_role("pending")
        app.security.datastore.remove_role_from_user(user, pending_role)

        app.security.datastore.commit()

    return redirect("admin/user_management")


@actions.route('/create_admin', methods=['POST'])
@roles_required('admin')
def create_admin():
    # log info
    form = MakeAdminForm(request.form)
    log.debug("create_admin {}".format(form))

    if form.user_to_make_admin.data is not None:
        user = app.security.datastore.find_user(
            id=form.user_to_make_admin.data)

        user_role = app.security.datastore.find_role("admin")
        app.security.datastore.add_role_to_user(user, user_role)

        pending_role = app.security.datastore.find_role("user")
        app.security.datastore.remove_role_from_user(user, pending_role)

        app.security.datastore.commit()

    return redirect("admin/user_management")


@actions.route('/delete_user', methods=['POST'])
@roles_required('admin')
def delete_user():
    # log info
    form = DeleteUserForm(request.form)
    log.debug("delete user {}".format(form))

    if form.user_to_delete.data is not None:
        db.session.query(User).filter(
            User.id == form.user_to_delete.data).delete()
        db.session.commit()

    return redirect("admin/user_management")


@actions.route('/new/password', methods=['POST'])
@login_required
def set_new_password():
    # log info
    form = ChangePasswordForm(request.form)
    user = app.security.datastore.get_user(session['user_id'])
    old_password = user.password
    _status = 'empty'

    if form.validate_on_submit():
        if form.old_password.data is not None:
            log.debug(
                "verify: {}".format(
                    verify_password(
                        form.old_password.data,
                        old_password)))
            if verify_password(form.old_password.data, old_password):
                log.debug("password_match")
                user = User.query.filter_by(username=user.username).first()
                user.password = hash_password(form.password.data)
                db.session.commit()
                _status = 'success'
            else:
                _status = 'wrong_old_password'

    return render_template("new_password.htm",
                           password_change=form,
                           status=_status
                           )


@actions.route('/password_change', methods=['GET'])
@login_required
def password_change():
    # log info
    _password_change = ChangePasswordForm()
    _password_change.validate_on_submit()
    return render_template("new_password.htm",
                           password_change=_password_change,
                           status=None
                           )
