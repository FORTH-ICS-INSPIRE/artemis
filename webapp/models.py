from webapp.shared import db, app
from sqlalchemy import Column, Integer, String, Float, \
    desc, Boolean, UniqueConstraint, DateTime
import time


# class Role(db.Model):
#     __tablename__ = 'roles'
#     id = Column(Integer(), primary_key=True)
#     name = Column(String(80), unique=True)
#     description = Column(String(255))


class User(db.Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True)
    password = Column(String(255))
    # active = Column(Boolean())
    # confirmed_at = Column(DateTime())
    # roles = db.relationship('Role')

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def get_id(self):
        return self.id

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def __repr__(self):
        return '<User id:{}, username:{}, password:{}>'.format(
            self.id, self.username, self.password)


class Monitor(db.Model):
    __tablename__ = 'monitors'
    id = Column(Integer, primary_key=True, autoincrement=True)
    prefix = Column(String(22))
    origin_as = Column(String(6))
    peer_as = Column(String(6))
    as_path = Column(String(100))
    service = Column(String(50))
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
            'timestamp'
        ),
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
            self.as_path = ''
            self.origin_as = ''
            self.peer_as = ''
        self.timestamp = msg['timestamp']
        self.hijack_id = None
        self.handled = False

    def __repr__(self):
        repr_str = '[\n'
        repr_str += '\tTYPE:         {}\n'.format(self.type)
        repr_str += '\tPREFIX:       {}\n'.format(self.prefix)
        repr_str += '\tORIGIN AS:    {}\n'.format(self.origin_as)
        repr_str += '\tPEER AS:      {}\n'.format(self.peer_as)
        repr_str += '\tAS PATH:      {}\n'.format(self.as_path)
        repr_str += '\tSERVICE:      {}\n'.format(self.service)
        repr_str += '\tTIMESTAMP:    {}\n'.format(self.timestamp)
        repr_str += ']'
        return repr_str


class Hijack(db.Model):
    __tablename__ = 'hijacks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(1))
    prefix = Column(String(22))
    hijack_as = Column(String(6))
    num_peers_seen = Column(Integer)
    num_asns_inf = Column(Integer)
    time_started = Column(Float)
    time_last = Column(Float)
    time_ended = Column(Float)
    mitigation_started = Column(Float)

    def __init__(self, msg, asn, htype):
        self.type = htype
        self.prefix = msg.prefix
        self.hijack_as = asn
        self.num_peers_seen = 1
        inf_asns_to_ignore = int(self.type) + 1
        self.num_asns_inf = len(
            set(msg.as_path.split(' ')[:-inf_asns_to_ignore]))
        self.time_started = msg.timestamp
        self.time_last = msg.timestamp
        self.time_ended = None
        self.mitigation_started = None

    def __repr__(self):
        repr_str = '[\n'
        repr_str += '\tTYPE:         {}\n'.format(self.type)
        repr_str += '\tPREFIX:       {}\n'.format(self.prefix)
        repr_str += '\tHIJACK AS:    {}\n'.format(self.hijack_as)
        repr_str += '\tTIME STARTED: {}\n'.format(self.time_started)
        repr_str += ']'
        return repr_str
