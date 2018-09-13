from flask import Blueprint
from webapp.cache import cache
from webapp.core import app
from flask_security.decorators import login_required, roles_required
from flask import url_for, render_template, request, redirect
from webapp.utils import log

import time

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/bgpupdates/', methods=['GET'])
@login_required
def display_monitors():
    prefixes_list = app.config['CONFIG'].get_prefixes_list()
    return render_template('bgpupdates.htm', prefixes=prefixes_list)

@main.route('/hijacks/', methods=['GET'])
@login_required
def display_hijacks():
    prefixes_list = app.config['CONFIG'].get_prefixes_list()
    return render_template('hijacks.htm', prefixes=prefixes_list)

@main.route('/hijack', methods=['GET'])
@login_required
def display_hijack():
    id_ = request.args.get('id')
    return render_template('hijack.htm', hijack_key = id_)


@main.route('/hijacks/mitigate/', methods=['GET'])
@roles_required('admin')
def mitigate_hijack():
    hijack_id = request.args.get('id')
    return redirect('/main/hijacks?id={}&action=mitigate'.format(hijack_id))




@main.route('/hijacks/resolved/', methods=['GET'])
@roles_required('admin')
def resolved_hijack():
    hijack_id = request.args.get('id')
    return redirect('/main/hijacks?id={}&action=resolved'.format(hijack_id))