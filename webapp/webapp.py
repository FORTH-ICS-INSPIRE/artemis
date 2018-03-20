from flask import url_for, render_template, request
from flask_nav import Nav
from flask_nav.elements import Navbar, View
from webapp.forms import CheckboxForm
import _thread
from webapp.tables import MonitorTable, HijackTable
from webapp.models import Monitor, Hijack
from webapp.shared import db, app
from sqlalchemy import desc


class WebApplication():

    def __init__(self):
        self.nav = Nav()
        self.nav.register_element('top', Navbar(
            View('Home', 'index'),
            View('Monitors', 'show_monitors'),
            View('Hijacks', 'show_hijacks')
        ))
        self.app = app
        self.db = db
        self.webapp_ = None
        self.flag = False

    @app.route('/', methods=['GET', 'POST'])
    def index():
        form = CheckboxForm()

        conf = None
        with open('configs/config','r') as f:
            conf = f.read()

        if request.method == 'POST' and form.validate_on_submit():
            if form.monitor.data:
                app.config['monitor'].start()
            else:
                app.config['monitor'].stop()
            if form.detector.data:
                app.config['detector'].start()
            else:
                app.config['detector'].stop()
            # if form.mitgator.data:
            #     app.config['mitgator'].start()
            # else:
            #     app.config['mitgator'].stop()
        else:
            form.monitor.data = app.config['monitor'].flag
            form.detector.data = app.config['detector'].flag
            # form.mitigator.data = app.config['mitigator'].flag
            form.mitigator.data = False

        return render_template('index.html', config=conf, form=form)

    @app.route('/monitors', methods=['GET', 'POST'])
    def show_monitors():
        sort = request.args.get('sort', 'id')
        reverse = (request.args.get('direction', 'asc') == 'desc')
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
        return render_template('show.html', data=data, type='Monitor')

    @app.route('/hijacks', methods=['GET', 'POST'])
    def show_hijacks():
        sort = request.args.get('sort', 'id')
        reverse = (request.args.get('direction', 'asc') == 'desc')
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
        return render_template('show.html', data=data, type='Hijack')

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    def run(self):
        self.db.init_app(app)
        self.nav.init_app(app)
        self.app.run(debug=False, host=self.app.config['WEBAPP_HOST'], port=self.app.config['WEBAPP_PORT'])

    def start(self):
        if not self.flag:
            self.webapp_ = _thread.start_new_thread(self.run, ())
            self.flag = True
            print('WebApplication Started..')

    def stop(self):
        if self.flag:
            self.flag = False
            print('WebApplication Stopped..')
