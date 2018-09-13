from flask import Blueprint
from webapp.core import app
from flask_security.decorators import login_required, roles_required
from flask import url_for, render_template, request, redirect
from webapp.core.actions import Resolve_hijack, Mitigate_hijack
from webapp.utils import log
from flask import jsonify
import time

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/bgpupdates/', methods=['GET'])
@login_required
def display_monitors():
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('bgpupdates.htm', prefixes=prefixes_list)

@main.route('/hijacks/', methods=['GET'])
@login_required
def display_hijacks():
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('hijacks.htm', prefixes=prefixes_list)

@main.route('/hijack', methods=['GET'])
@login_required
def display_hijack():
    id_ = request.args.get('id')
    return render_template('hijack.htm', hijack_key = id_)

@main.route('/hijacks/resolve/', methods=['GET'])
@roles_required('admin')
def resolved_hijack():
    hijack_key = request.args.get('id')
    resolve_hijack_ = Resolve_hijack(hijack_key)
    resolve_hijack_.resolve()
    return jsonify({'status': 'success'})


@main.route('/hijacks/mitigate/', methods=['GET'])
@roles_required('admin')
def mitigate_hijack():
    hijack_key = request.args.get('id')
    prefix = request.args.get('prefix')
    mitigate_hijack_ = Mitigate_hijack(hijack_key, prefix)
    mitigate_hijack_.mitigate()
    return jsonify({'status': 'success'})