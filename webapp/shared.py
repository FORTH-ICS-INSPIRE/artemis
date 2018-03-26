from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask_login import LoginManager
from flask_hashing import Hashing
from flask_nav import Nav
from flask import Flask

print('Shared Variables Initialization..')

app = Flask(__name__)
app.config.from_pyfile('../configs/webapp.cfg')

Bootstrap(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
hashing = Hashing(app)
nav = Nav(app)

db_session = db.session


def getOrCreate(model, defaults=None, **kwargs):
    instance = db_session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        params = kwargs
        params.update(defaults or {})
        instance = model(**params)
        db_session.add(instance)
        db_session.commit()
        return instance, True