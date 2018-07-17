from flask import Blueprint
from webapp.cache import cache
from webapp import app
from flask_security.decorators import login_required, roles_required
from flask import url_for, render_template, request, redirect
from sqlalchemy import desc, and_, exc
from webapp.data.tables import MonitorTable, HijackTable
from webapp.data.models import Monitor, Hijack, db
import time

main = Blueprint('main', __name__, template_folder='templates')

@main.route('/monitors/', methods=['GET', 'POST'])
@login_required
def display_monitors():
    sort = request.args.get('sort', 'id')
    reverse = (request.args.get('direction', 'desc') == 'desc')
    if reverse:
        data = MonitorTable(
            Monitor.query.order_by(
                desc(getattr(
                    Monitor, sort
                ))).all(),
            sort_by=sort,
            sort_reverse=reverse)
    else:
        data = MonitorTable(
            Monitor.query.order_by(
                getattr(
                    Monitor, sort
                )).all(),
            sort_by=sort,
            sort_reverse=reverse)
    return render_template('show.htm', data=data, type='Monitor')

@main.route('/hijacks/', methods=['GET', 'POST'])
@login_required
def display_hijacks():
    sort = request.args.get('sort', 'id')
    hijack_id = request.args.get('id', None)
    hijack_action = request.args.get('action', None)
    reverse = (request.args.get('direction', 'desc') == 'desc')
    if reverse:
        data = HijackTable(
            Hijack.query.order_by(
                desc(getattr(
                    Hijack, sort
                ))).all(),
            sort_by=sort,
            sort_reverse=reverse)
    else:
        data = HijackTable(
            Hijack.query.order_by(
                getattr(
                    Hijack, sort
                )).all(),
            sort_by=sort,
            sort_reverse=reverse)

    if hijack_id is not None and hijack_action is not None:
        time_now = time.time()
        hijack_event = Hijack.query.filter(
            Hijack.id.like(hijack_id)
        ).first()

        if hijack_event is not None:

            if hijack_action == 'resolved':
                if hijack_event.time_ended is None:
                    hijack_event.time_ended = time_now
                    hijack_event.to_mitigate = False
                    db.session.add(hijack_event)
                    db.session.commit()

            elif hijack_action == 'mitigate':
                if not hijack_event.to_mitigate and hijack_event.mitigation_started is None and hijack_event.time_ended is None:
                    hijack_event.to_mitigate = True
                    db.session.add(hijack_event)
                    db.session.commit()

                    if app.config['mitigator'].flag:
                        app.config['mitigator'].hijack_queue.put(int(hijack_id))

        return redirect('/main/hijacks')

    return render_template('show.htm', data=data, type='Hijack')

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
