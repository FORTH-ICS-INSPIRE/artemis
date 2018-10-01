from flask import Blueprint
from webapp.core import app
from flask_security.decorators import login_required, roles_required, roles_accepted
from flask import url_for, render_template, request, redirect
from webapp.core.actions import Resolve_hijack, Mitigate_hijack, Ignore_hijack, Comment_hijack
from webapp.core.modules import Modules_status
from flask import jsonify
from webapp.core.fetch_hijack import get_hijack_by_key
import logging
import time
import json

log = logging.getLogger('webapp_logger')

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/bgpupdates/', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_monitors():
    #log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('bgpupdates.htm', prefixes=prefixes_list)




@main.route('/hijacks/', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_hijacks():
    #log debug
    prefixes_list = app.config['configuration'].get_prefixes_list()
    return render_template('hijacks.htm', prefixes=prefixes_list)




@main.route('/hijack', methods=['GET'])
@login_required
@roles_accepted('admin', 'user')
def display_hijack():
    #log debug
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

    _comment = hijack_data['comment']
    del hijack_data['comment']


    return render_template('hijack.htm', 
        data = json.dumps(hijack_data), 
        mitigate = _mitigation_flag, 
        configured = _configured,
        comment = _comment )




@main.route('/hijacks/resolve/', methods=['GET'])
@roles_required('admin')
def resolved_hijack():
    #log info
    hijack_key = request.args.get('id')
    log.debug('url: /hijacks/resolve/{}'.format(hijack_key))
    resolve_hijack_ = Resolve_hijack(hijack_key)
    resolve_hijack_.resolve()
    return jsonify({'status': 'success'})



@main.route('/hijacks/mitigate/', methods=['GET'])
@roles_required('admin')
def mitigate_hijack():
    #log info
    hijack_key = request.args.get('id')
    prefix = request.args.get('prefix')

    try:
        _mitigate_hijack = Mitigate_hijack(hijack_key, prefix)
        _mitigate_hijack.mitigate()
    except:
        log.debug("mitigate_hijack failed")
    
    return jsonify({'status': 'success'})



@main.route('/hijacks/ignore/', methods=['GET'])
@roles_required('admin')
def ignore_hijack():
    #log info
    hijack_key = request.args.get('id')

    try:
        _ignore_hijack = Ignore_hijack(hijack_key)
        _ignore_hijack.ignore()

    except:
        log.debug("ignore_hijack failed")
    
    return jsonify({'status': 'success'})



@main.route('/submit_comment/', methods=['POST'])
@roles_required('admin')
def handle_new_comment():
    #log info
    new_comment = request.values.get('new_comment')
    hijack_key = request.values.get('hijack_key')
    log.debug("hijack_key: {0} new_comment: {1}".format(hijack_key, new_comment))

    comment_ =  Comment_hijack()
    response, success = comment_.send(hijack_key, new_comment)

    if success == True:
        return jsonify({'status': 'success', 'data': new_comment, 'response': response})
    else:
        return jsonify({'status': 'fail', 'data': new_comment, 'response': response})


