from flask_security import RoleMixin
from flask_security import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

roles_users = db.Table(
    "roles_users",
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id")),
    db.Column("role_id", db.Integer(), db.ForeignKey("role.id")),
)


class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<Role %r>" % (self.name)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, index=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    valid = db.Column(db.Boolean(), default=False)
    active = db.Column(db.Boolean())
    last_login_at = db.Column(
        db.DateTime(timezone=False), default=db.func.current_timestamp()
    )
    current_login_at = db.Column(db.DateTime(timezone=False))
    last_login_ip = db.Column(db.String(255))
    current_login_ip = db.Column(db.String(255))
    login_count = db.Column(db.BigInteger, default=0)
    roles = db.relationship(
        "Role", secondary=roles_users, backref=db.backref("users", lazy="dynamic")
    )

    def __init__(self, username, email, password, active, roles):
        self.username = username
        self.email = email
        self.password = password
        self.active = active
        self.roles = roles

    def __repr__(self):
        return "<User %r>" % (self.email)

    def has_roles(self, *args):
        return set(args).issubset({role.name for role in self.roles})
