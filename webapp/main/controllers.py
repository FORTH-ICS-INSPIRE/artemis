from flask import Blueprint
from webapp.cache import cache
from flask_security.decorators import login_required

main = Blueprint('main', __name__)

@main.route('/monitors/')
@login_required
def display_monitors():
    return 'monitors'

@main.route('/hijacks/')
@login_required
def display_hijacks():
    return 'hijacks'

@main.route('/status/')
@login_required
def display_status():
    return 'status'
