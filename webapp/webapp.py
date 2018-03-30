from flask import url_for, render_template, request, redirect
from flask_nav.elements import Navbar, View
from webapp.forms import CheckboxForm, ConfigForm, LoginForm
import _thread
from webapp.models import Monitor, Hijack, User
from webapp.shared import app, db, db_session, login_manager, \
    getOrCreate, hashing, nav
from webapp.tables import MonitorTable, HijackTable
from sqlalchemy import desc, and_, exc
import logging
from flask_login import UserMixin, login_required, login_user, logout_user
import time


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


class WebApplication():

    def __init__(self):
        self.app = app
        self.webapp_ = None
        self.flag = False

    @app.before_first_request
    def create_all():
        nav.register_element('top', Navbar(
            View('Home', 'index'),
            View('Monitors', 'show_monitors'),
            View('Hijacks', 'show_hijacks'),
            View('Logout', 'logout')
        ))
        db.create_all()
        login_manager.login_view = 'login'
        getOrCreate(User, username='test', password=hashing.hash_value('test'))

    @login_manager.user_loader
    def load_user(user):
        return User.query.get(user)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        login_form = LoginForm()
        if login_form.validate_on_submit():

            user = User.query.filter(and_(
                User.username.like(login_form.username.data)
            )).first()

            if user and hashing.check_value(user.password, login_form.password.data):
                login_user(user, remember=login_form.remember_me.data)
                next_page = request.args.get('next')
                if not next_page:
                    next_page = '/'
                return redirect(next_page)
            else:
                error = 'Wrong Username/Password'
                return render_template('login.html', login_form=login_form, error=error)

        else:
            return render_template('login.html', login_form=login_form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect('login')

    @app.route('/', methods=['GET', 'POST'])
    @login_required
    def index():
        form = CheckboxForm()
        config_form = ConfigForm()

        with open('configs/config', 'r') as f:
            config_form.config.data = f.read()

        if form.validate_on_submit():
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

        return render_template('index.html', config=config_form, form=form)

    @app.route('/monitors', methods=['GET', 'POST'])
    @login_required
    def show_monitors():
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
        return render_template('show.html', data=data, type='Monitor')

    @app.route('/hijacks', methods=['GET', 'POST'])
    @login_required
    def show_hijacks():
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
                        db_session.add(hijack_event)
                        db_session.commit()

                elif hijack_action == 'mitigate':
                    if hijack_event.mitigation_started is None and hijack_event.time_ended is None:
                        hijack_event.mitigation_started = time_now
                        db_session.add(hijack_event)
                        db_session.commit()

            return redirect('/hijacks')

        return render_template('show.html', data=data, type='Hijack')

    @app.route('/hijacks/mitigate', methods=['GET', 'POST'])
    @login_required
    def mitigate_hijack():
        hijack_id = request.args.get('id')
        return redirect('/hijacks?id={}&action=mitigate'.format(hijack_id))

    @app.route('/hijacks/resolved', methods=['GET', 'POST'])
    @login_required
    def resolved_hijack():
        hijack_id = request.args.get('id')
        return redirect('/hijacks?id={}&action=resolved'.format(hijack_id))

    def run(self):
        self.app.run(
            debug=False,
            host=self.app.config['WEBAPP_HOST'],
            port=self.app.config['WEBAPP_PORT']
        )

    def start(self):
        if not self.flag:
            self.webapp_ = _thread.start_new_thread(self.run, ())
            self.flag = True
            print('WebApplication Started..')

    def stop(self):
        if self.flag:
            self.flag = False
            print('WebApplication Stopped..')
