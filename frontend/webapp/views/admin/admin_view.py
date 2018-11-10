from flask import Blueprint, render_template, redirect, request, jsonify
from flask_security.decorators import roles_required, roles_accepted
from webapp.data.models import User, Role
from webapp.templates.forms import ApproveUserForm, MakeAdminForm, DeleteUserForm
from webapp.core import app
from webapp.core.actions import Submit_new_config
from webapp.core.fetch_config import fetch_all_config_timestamps
import logging
import json

log = logging.getLogger('webapp_logger')

admin = Blueprint('admin', __name__, template_folder='templates')


@admin.route('/', methods=['GET', 'POST'])
@roles_required('admin')
def default():
    return redirect("admin/system")


@admin.route('/system', methods=['GET', 'POST'])
@roles_required('admin')
def index():
    return render_template('system.htm')


@admin.route('/config', methods=['POST'])
@roles_required('admin')
def handle_new_config():
    try:
        app.config['configuration'].get_newest_config()
        old_config = app.config['configuration'].get_raw_config()
        data = json.loads(request.data)
        comment = data['comment']
        new_config = data['new_config']
        config_modify = Submit_new_config()
        response, success = config_modify.send(new_config, old_config, comment)

        if success:
            return jsonify(
                {'status': 'success', 'response': response})
        else:
            return jsonify(
                {'status': 'fail', 'response': response})
    except Exception as e:
        log.exception("")
        return jsonify(
            {'status': 'fail', 'response': str(e)})


@admin.route('/user_management', methods=['GET'])
@roles_required('admin')
def user_management():
    # log info
    _pending_users_form = ApproveUserForm()

    _pending_users_list = []
    _pending_users = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("pending")).id]))).all()

    for _pending_user in _pending_users:
        _pending_users_list.append((_pending_user.id, _pending_user.username))

    _pending_users_form.user_to_approve.choices = _pending_users_list

    _users_to_promote_to_admin = MakeAdminForm()
    _users_list = []
    _users = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("user")).id]))).all()

    for _user in _users:
        _users_list.append((_user.id, _user.username))

    _users_to_promote_to_admin.user_to_make_admin.choices = _users_list

    _users_to_delete = DeleteUserForm()
    _users_to_delete.user_to_delete.choices = _pending_users_list + _users_list

    user_list = []
    _admins = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("admin")).id]))).all()

    for user in _pending_users:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'pending',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )

    for user in _users:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'user',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )
    for user in _admins:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )

    return render_template('user_management.htm',
                           users_to_approve_form=_pending_users_form,
                           users_to_make_admin_form=_users_to_promote_to_admin,
                           users_to_delete_form=_users_to_delete,
                           users_list=user_list
                           )


@admin.route('/config_comparison', methods=['GET'])
@roles_accepted('admin', 'user')
def config_comparison():
    # log info
    _configs = fetch_all_config_timestamps()
    return render_template('config_comparison.htm',
                           configs=list(reversed(_configs)))
