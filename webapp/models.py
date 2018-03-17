from webapp.shared import db
from sqlalchemy import Column, Integer, String, Float, desc


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
            self.service = msg['service']
            self.type = msg['type']
            if self.type == 'A':
                self.origin_as = msg['as_path'][-1]
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

    def __init__(self, msg, htype):
        self.type = htype
        self.prefix = msg['prefix']
        if htype == 0:
            self.hijack_as = msg['as_path'][-1]
        else:
            self.hijack_as = msg['as_path'][-2]
        self.num_peer = 0
        self.num_asns_in = 0
        self.time_started = time.time()
        self.time_last = None
        self.time_ended = None
