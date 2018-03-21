from webapp.shared import db
from sqlalchemy import Column, Integer, String, Float, desc, Boolean, UniqueConstraint
import time


class Monitor(db.Model):
    __tablename__ = 'monitor'
    id = Column(Integer, primary_key=True, autoincrement=True)
    prefix = Column(String(22))
    origin_as = Column(String(6))
    peer_as = Column(String(6))
    as_path = Column(String(100))
    service = Column(String(14))
    type = Column(String(1))
    timestamp = Column(Float)
    hijack_id = Column(Integer, nullable=True)
    handled = Column(Boolean)

    __table_args__ = (
        UniqueConstraint(
            'prefix',
            'origin_as',
            'peer_as',
            'as_path',
            'service',
            'type',
            'timestamp',
            'hijack_id' 
        )
    )

    def __init__(self, msg):
        self.prefix = msg['prefix']
        self.service = msg['service']
        self.type = msg['type']
        if self.type == 'A':
            self.as_path = ' '.join(map(str, msg['as_path']))
            self.origin_as = str(msg['as_path'][-1])
            self.peer_as = str(msg['as_path'][0])
        else:
            self.as_path = None
        self.timestamp = msg['timestamp']
        self.hijack_id = None
        self.handled = False


class Hijack(db.Model):
    __tablename__ = 'hijack'
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(1))
    prefix = Column(String(22))
    hijack_as = Column(String(6))
    num_peers = Column(Integer)
    num_asns_inf = Column(Integer)
    time_started = Column(Float)
    time_last = Column(Float)
    time_ended = Column(Float)

    def __init__(self, msg, asn, htype):
        self.type = htype
        self.prefix = msg.prefix
        self.hijack_as = asn
        self.num_peer = 0
        self.num_asns_in = 0
        self.time_started = time.time()
        self.time_last = None
        self.time_ended = None
