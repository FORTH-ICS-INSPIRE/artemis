from sqlalchemy import exc
from flask import Blueprint, render_template, flash
from flask import current_app, redirect, request, url_for, jsonify
from flask_security.decorators import roles_required
from webapp.data.models import User, db, Role, roles_users
from webapp.templates.forms import CheckboxForm, ApproveUserForm, MakeAdminForm, DeleteUserForm
from webapp.core import app
from webapp.core.modules import Modules_status
from webapp.core.actions import New_config
import yaml
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
    #log info
    form = CheckboxForm()
    app.config['configuration'].get_newest_config()

    status_request = Modules_status()
    status_request.call('all', 'status')
    app.config['status'] = status_request.get_response_all()

    if form.validate_on_submit():
        if form.monitor.data:
            status_request.call('monitor', 'start')
        else:
            status_request.call('monitor', 'stop')
        if form.detector.data:
            status_request.call('detection', 'start')
        else:
            status_request.call('detection', 'stop')
        if form.mitigator.data:
            status_request.call('mitigation', 'start')
        else:
            status_request.call('mitigation', 'stop')
    else:
        if app.config['status']['monitor']['status'] == 'up':
            form.monitor.data = True
        else:
            form.monitor.data = False
        if app.config['status']['detection']['status'] == 'up':
            form.detector.data = True
        else:
            form.detector.data = False
        if app.config['status']['mitigation']['status'] == 'up':
            form.mitigator.data = True
        else:
            form.mitigator.data = False

    return render_template('system.htm', 
        form=form, 
        config=app.config['configuration'].get_raw_config(), 
        config_timestamp = app.config['configuration'].get_config_last_modified() )


@admin.route('/config/', methods=['POST'])
@roles_required('admin')
def handle_new_config():
    #log info
    app.config['configuration'].get_newest_config()
    old_config = app.config['configuration'].get_raw_config()
    config_modify = New_config()
    new_config = request.values.get('new_config')
    response, success = config_modify.send(new_config, old_config)

    if success == True:
        return jsonify({'status': 'success', 'data': new_config, 'response': response})
    else:
        return jsonify({'status': 'fail', 'data': new_config, 'response': response})


@admin.route('/user_management', methods=['GET'])
@roles_required('admin')
def user_management():
    #log info
    _pending_users_form = ApproveUserForm()

    _pending_users_list = []
    _pending_users = User.query.filter(User.roles.any(Role.id.in_([(app.security.datastore.find_role("pending")).id]))).all()

    for _pending_user in _pending_users:
        _pending_users_list.append( (_pending_user.id, _pending_user.username) )

    _pending_users_form.user_to_approve.choices = _pending_users_list


    _users_to_promote_to_admin = MakeAdminForm() 
    _users_list = []
    _users = User.query.filter(User.roles.any(Role.id.in_([(app.security.datastore.find_role("user")).id]))).all()

    for _user in _users:
        _users_list.append( (_user.id, _user.username) )

    _users_to_promote_to_admin.user_to_make_admin.choices = _users_list

    _users_to_delete = DeleteUserForm()
    _users_to_delete.user_to_delete.choices = _pending_users_list + _users_list

    return render_template('user_management.htm', 
        users_to_approve_form=_pending_users_form, 
        users_to_make_admin_form=_users_to_promote_to_admin,
        users_to_delete_form=_users_to_delete)


@admin.route('/approve_user', methods=['POST'])
@roles_required('admin')
def approve_user():
    #log info
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


@admin.route('/create_admin', methods=['POST'])
@roles_required('admin')
def create_admin():
    #log info
    form = MakeAdminForm(request.form)
    log.debug("create_admin {}".format(form))

    if form.user_to_make_admin.data is not None:
        user = app.security.datastore.find_user(id=form.user_to_make_admin.data)
        
        user_role = app.security.datastore.find_role("admin")
        app.security.datastore.add_role_to_user(user, user_role)

        pending_role = app.security.datastore.find_role("user")
        app.security.datastore.remove_role_from_user(user, pending_role)

        app.security.datastore.commit()

    return redirect("admin/user_management")



@admin.route('/delete_user', methods=['POST'])
@roles_required('admin')
def delete_user():
    #log info
    form = DeleteUserForm(request.form)
    log.debug("delete user {}".format(form))

    if form.user_to_delete.data is not None:
        db.session.query(User).filter(User.id==form.user_to_delete.data).delete()
        db.session.commit()

    return redirect("admin/user_management")
