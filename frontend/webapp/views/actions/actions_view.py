from flask import Blueprint, render_template, session, current_app as app
from flask import redirect, request, jsonify
from flask_security.decorators import roles_required, login_required
from flask_security.utils import hash_password, verify_password
from webapp.data.models import db, User
from webapp.templates.forms import ApproveUserForm, MakeAdminForm, RemoveAdminForm, DeleteUserForm, ChangePasswordForm
from webapp.core.actions import Resolve_hijack, Mitigate_hijack, Ignore_hijack, Comment_hijack, Seen_hijack, Hijacks_multiple_action
from webapp.core.modules import Modules_state
import json

actions = Blueprint('actions', __name__, template_folder='templates')


@actions.route('/hijacks/resolve/', methods=['POST'])
@roles_required('admin')
def resolve_hijack():
    # log info
    hijack_key = request.values.get('hijack_key')
    prefix = request.values.get('prefix')
    type_ = request.values.get('type_')
    hijack_as = int(request.values.get('hijack_as'))
    app.artemis_logger.debug('url: /hijacks/resolve/{}'.format(hijack_key))
    resolve_hijack_ = Resolve_hijack(hijack_key, prefix, type_, hijack_as)
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
        app.artemis_logger.debug('mitigate_hijack failed')

    return jsonify({'status': 'success'})


@actions.route('/hijacks/ignore/', methods=['POST'])
@roles_required('admin')
def ignore_hijack():
    hijack_key = request.values.get('hijack_key')
    prefix = request.values.get('prefix')
    type_ = request.values.get('type_')
    hijack_as = int(request.values.get('hijack_as'))

    try:
        _ignore_hijack = Ignore_hijack(hijack_key, prefix, type_, hijack_as)
        _ignore_hijack.ignore()

    except BaseException:
        app.artemis_logger.debug('ignore_hijack failed')

    return jsonify({'status': 'success'})


@actions.route('/submit_comment/', methods=['POST'])
@roles_required('admin')
def submit_new_comment():
    new_comment = request.values.get('new_comment')
    hijack_key = request.values.get('hijack_key')
    app.artemis_logger.debug(
        'hijack_key: {0} new_comment: {1}'.format(
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
    form = ApproveUserForm(request.form)
    app.artemis_logger.debug('approve_user {}'.format(form))

    if form.select_field.data is not None:
        user = app.security.datastore.find_user(id=form.select_field.data)

        user_role = app.security.datastore.find_role('user')
        app.security.datastore.add_role_to_user(user, user_role)

        pending_role = app.security.datastore.find_role('pending')
        app.security.datastore.remove_role_from_user(user, pending_role)

        app.security.datastore.commit()

    return redirect('admin/user_management')


@actions.route('/create_admin', methods=['POST'])
@roles_required('admin')
def create_admin():
    form = MakeAdminForm(request.form)
    app.artemis_logger.debug('create_admin {}'.format(form))

    if form.select_field.data is not None:
        user = app.security.datastore.find_user(
            id=form.select_field.data)

        admin_role = app.security.datastore.find_role('admin')
        app.security.datastore.add_role_to_user(user, admin_role)

        user_role = app.security.datastore.find_role('user')
        app.security.datastore.remove_role_from_user(user, user_role)

        app.security.datastore.commit()

    return redirect('admin/user_management')


@actions.route('/remove_admin', methods=['POST'])
@roles_required('admin')
def remove_admin():
    form = RemoveAdminForm(request.form)
    app.artemis_logger.debug('remove_admin {}'.format(form))

    if form.select_field.data is not None:
        user = app.security.datastore.find_user(
            id=form.select_field.data)

        admin_role = app.security.datastore.find_role('admin')
        app.security.datastore.remove_role_from_user(user, admin_role)

        user_role = app.security.datastore.find_role('user')
        app.security.datastore.add_role_to_user(user, user_role)

        app.security.datastore.commit()

    return redirect('admin/user_management')


@actions.route('/delete_user', methods=['POST'])
@roles_required('admin')
def delete_user():
    form = DeleteUserForm(request.form)
    app.artemis_logger.debug('delete user {}'.format(form))

    if form.select_field.data is not None:
        db.session.query(User).filter(
            User.id == form.select_field.data).delete()
        db.session.commit()

    return redirect('admin/user_management')


@actions.route('/new/password', methods=['POST'])
@login_required
def set_new_password():
    form = ChangePasswordForm(request.form)
    user = app.security.datastore.get_user(session['user_id'])
    old_password = user.password
    _status = 'empty'

    if form.validate_on_submit():
        if form.old_password.data is not None:
            app.artemis_logger.debug(
                'verify: {}'.format(
                    verify_password(
                        form.old_password.data,
                        old_password)))
            if verify_password(form.old_password.data, old_password):
                app.artemis_logger.debug('password_match')
                user = User.query.filter_by(username=user.username).first()
                user.password = hash_password(form.password.data)
                db.session.commit()
                _status = 'success'
            else:
                _status = 'wrong_old_password'

    return render_template('new_password.htm',
                           password_change=form,
                           status=_status
                           )


@actions.route('/password_change', methods=['GET'])
@login_required
def password_change():
    _password_change = ChangePasswordForm()
    _password_change.validate_on_submit()
    return render_template('new_password.htm',
                           password_change=_password_change,
                           status=None
                           )


@actions.route('/modify_state', methods=['POST'])
@roles_required('admin')
def monitor_state():
    try:
        modules_state = Modules_state()
        data = json.loads(request.data)
        if data['state']:
            modules_state.call(data['name'], 'start')
        else:
            modules_state.call(data['name'], 'stop')
        return json.dumps({'success': True}), 200, {
            'ContentType': 'application/json'}
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}), 500, {
            'ContentType': 'application/json'}


@actions.route('/submit_hijack_seen', methods=['POST'])
@roles_required('admin')
def submit_hijack_seen():
    hijack_key = request.values.get('hijack_key')
    state = request.values.get('state')

    seen_ = Seen_hijack()
    success = seen_.send(hijack_key, state)

    if success:
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'fail'})


@actions.route('/hijacks_actions', methods=['POST'])
@roles_required('admin')
def submit_hijacks_actions():
    hijack_keys = json.loads(request.values.get('hijack_keys'))
    action = request.values.get('action')

    multiple_action_ = Hijacks_multiple_action()
    success = multiple_action_.send(hijack_keys, action)

    if success:
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'fail'})
