from flask import Blueprint
from webapp.cache import cache
from webapp.core import app
from flask_security.decorators import login_required, roles_required
from flask import url_for, render_template, request, redirect
from sqlalchemy import desc, and_, exc
from webapp.data.models import db
from flask import jsonify

import time

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/monitors/', methods=['GET', 'POST'])
@login_required
def display_monitors():
    #prefixes_list = app.config['config'].getPrefixes_list()
    return render_template('bgpupdates.htm')#, prefixes=prefixes_list)


@main.route('/hijacks/', methods=['GET', 'POST'])
@login_required
def display_hijacks():
    return render_template('hijacks.htm')



@main.route('/hijacks/mitigate/', methods=['GET', 'POST'])
@roles_required('admin')
def mitigate_hijack():
    hijack_id = request.args.get('id')
    return redirect('/main/hijacks?id={}&action=mitigate'.format(hijack_id))

@main.route('/hijacks/resolved/', methods=['GET', 'POST'])
@roles_required('admin')
def resolved_hijack():
    hijack_id = request.args.get('id')
    return redirect('/main/hijacks?id={}&action=resolved'.format(hijack_id))