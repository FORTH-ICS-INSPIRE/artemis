from flask import Blueprint
from webapp.core import app
from flask_security.decorators import login_required, roles_required
from flask import url_for, render_template, request, redirect
from webapp.core.actions import Resolve_hijack, Mitigate_hijack
from flask import jsonify
import logging
import time

log = logging.getLogger('artemis_logger')

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/bgpupdates/', methods=['GET'])
@login_required
def display_monitors():
    #log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('bgpupdates.htm', prefixes=prefixes_list)

@main.route('/hijacks/', methods=['GET'])
@login_required
def display_hijacks():
    #log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('hijacks.htm', prefixes=prefixes_list)

@main.route('/hijack', methods=['GET'])
@login_required
def display_hijack():
    #log debug
    id_ = request.args.get('id')
    return render_template('hijack.htm', hijack_key = id_)

@main.route('/hijacks/resolve/', methods=['GET'])
@roles_required('admin')
def resolved_hijack():
    #log info
    hijack_key = request.args.get('id')
    resolve_hijack_ = Resolve_hijack(hijack_key)
    resolve_hijack_.resolve()
    return jsonify({'status': 'success'})

@main.route('/hijacks/mitigate/', methods=['GET'])
@roles_required('admin')
def mitigate_hijack():
    #log info
    hijack_key = request.args.get('id')
    prefix = request.args.get('prefix')
    mitigate_hijack_ = Mitigate_hijack(hijack_key, prefix)
    mitigate_hijack_.mitigate()
    return jsonify({'status': 'success'})