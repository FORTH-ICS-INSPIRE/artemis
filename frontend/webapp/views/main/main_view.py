from flask import Blueprint
from webapp.core import app
from flask_security.decorators import login_required, roles_accepted
from flask import render_template, request
from webapp.core.modules import Modules_status
from webapp.core.fetch_hijack import get_hijack_by_key
import logging
import json

log = logging.getLogger('webapp_logger')

main = Blueprint('main', __name__, template_folder='templates')


@main.route('/bgpupdates/', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_monitors():
    # log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('bgpupdates.htm', prefixes=prefixes_list)


@main.route('/hijacks/', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_hijacks():
    # log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('hijacks.htm', prefixes=prefixes_list)


@main.route('/hijack', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_hijack():
    # log debug
    app.config['configuration'].get_newest_config()
    _key = request.args.get('key')
    mitigation_status_request = Modules_status()
    mitigation_status_request.call('mitigation', 'status')
    _mitigation_flag = False

    hijack_data = get_hijack_by_key(_key)
    _configured = False

    if 'configured_prefix' in hijack_data:
        if hijack_data['configured_prefix'] in app.config['configuration'].get_prefixes_list():
            _configured = True

    if mitigation_status_request.is_up_or_running('mitigation'):
        _mitigation_flag = True

    return render_template('hijack.htm',
                           data=json.dumps(hijack_data),
                           mitigate=_mitigation_flag,
                           configured=_configured
                           )
