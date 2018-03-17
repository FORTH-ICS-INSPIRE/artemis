from flask import url_for, render_template, request
from flask_nav import Nav
from flask_nav.elements import Navbar, View
from webapp.forms import CheckboxForm
from multiprocessing import Process
import grpc
import time
import math
import _thread
from protogrpc import service_pb2_grpc, service_pb2
from webapp.tables import MonitorTable, HijackTable
from webapp.models import Monitor, Hijack
from protobuf_to_dict import protobuf_to_dict
from webapp.shared import db
from webapp.shared import app
from sqlalchemy import desc


class WebApplication():

    def __init__(self):
        self.nav = Nav()
        self.nav.register_element('top', Navbar(
            View('Home', 'index'),
            View('Monitors', 'show_monitors'),
            View('Hijacks', 'show_hijacks')
        ))
        self.db = db
        self.db.init_app(app)
        self.nav.init_app(app)
        self.webapp_ = None
        self.flag = False

    @app.route('/', methods=['GET', 'POST'])
    def index():
        form = CheckboxForm()

        channel = grpc.insecure_channel('localhost:50051')
        stub = service_pb2_grpc.ServiceListenerStub(channel)
        if request.method == 'POST':
            stub.sendServiceHandle(service_pb2.ServiceMessage(
                monitor=form.monitor.data,
                detector=form.detector.data,
                mitigator=form.mitigator.data
            ))
        else:
            reply = protobuf_to_dict(
                stub.queryServiceState(service_pb2.Empty()))
            if 'monitor' in reply:
                form.monitor.data = True
            if 'detector' in reply:
                form.detector.data = True
            if 'mitigator' in reply:
                form.mitigator.data = True

        return render_template('index.html', form=form)

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
        app.run(debug=False)

    def start(self):
        if not self.flag:
            print('Starting WebApplication..')
            self.webapp_ = Process(target=self.run, args=())
            self.webapp_.start()
            self.flag = True

    def stop(self):
        if self.flag:
            print('Stopping WebApplication..')
            self.webapp_.terminate()
            self.flag = False
