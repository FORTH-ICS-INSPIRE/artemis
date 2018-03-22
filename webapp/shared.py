from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask import Flask

print('Shared Variables Initialization..')

app = Flask(__name__)
app.config.from_pyfile('../configs/webapp.cfg')

Bootstrap(app)
db = SQLAlchemy(app)
db_session = db.session
