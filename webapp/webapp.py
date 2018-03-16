from sqlalchemy import Column, Integer, String, Float, desc
from flask import Flask, url_for, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
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
from protobuf_to_dict import protobuf_to_dict

app = Flask(__name__)
app.config.from_pyfile('../configs/webapp.cfg')
db = SQLAlchemy(app)
Bootstrap(app)


class WebApplication():

    def __init__(self):
        self.nav = Nav()
        self.nav.register_element('top', Navbar(
            View('Home', 'index'),
            View('Monitors', 'show_monitors'),
            View('Hijacks', 'show_hijacks')
        ))
        self.db = db
        self.nav.init_app(app)
        self.webapp_ = None
        self.flag = False

    class Monitor(db.Model):
        __tablename__ = 'monitor'
        id = Column(Integer, primary_key=True)
        prefix = Column(String(22))
        origin_as = Column(String(5))
        as_path = Column(String(100))
        service = Column(String(14))
        type = Column(String(1))
        timestamp = Column(Float)
        hijack_id = Column(Integer, nullable=True)

        def __init__(self, msg):
            try:
                self.prefix = msg['prefix']
                self.origin_as = msg['origin_as']
                self.service = msg['service']
                self.type = msg['type']
                if (self.type == 'A'):
                    self.as_path = str(msg['as_path'])
                else:
                    self.as_path = None
                self.timestamp = msg['timestamp']
                self.hijack_id = None
            except:
                print(msg)

    class Hijack(db.Model):
        __tablename__ = 'hijack'
        id = Column(Integer, primary_key=True)
        type = Column(String(1))
        prefix = Column(String(22))
        hijack_as = Column(String(5))
        num_peers = Column(Integer)
        num_asns_inf = Column(Integer)
        time_started = Column(Float)
        time_last = Column(Float)
        time_ended = Column(Float)

        def __init__(self, msg):
            self.type = msg['type']
            self.prefix = msg['prefix']
            self.hijack_as = msg['hijack_as']
            self.num_peer = msg['num_peers']
            self.num_asns_in = msg['num_asns_inf']
            self.time_started = msg['time_started']
            self.time_last = msg['time_last']
            self.time_ended = msg['time_ended']

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
            reply = protobuf_to_dict(stub.queryServiceState(service_pb2.Empty()))
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
            data = MonitorTable(WebApplication.Monitor.query.order_by(desc(getattr(WebApplication.Monitor, sort))).limit(25).all(),
                                sort_by=sort,
                                sort_reverse=reverse)
        else:
            data = MonitorTable(WebApplication.Monitor.query.order_by(getattr(WebApplication.Monitor, sort)).limit(25).all(),
                                sort_by=sort,
                                sort_reverse=reverse)
        return render_template('show.html', data=data, type='Monitor')

    @app.route('/hijacks', methods=['GET', 'POST'])
    def show_hijacks():
        sort = request.args.get('sort', 'id')
        reverse = (request.args.get('direction', 'asc') == 'desc')
        if reverse:
            data = HijackTable(WebApplication.Hijack.query.order_by(desc(getattr(WebApplication.Hijack, sort))).limit(25).all(),
                               sort_by=sort,
                               sort_reverse=reverse)
        else:
            data = HijackTable(WebApplication.Hijack.query.order_by(getattr(WebApplication.Hijack, sort)).limit(25).all(),
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
