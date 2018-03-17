from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask import Flask

app = Flask(__name__)
app.config.from_pyfile('../configs/webapp.cfg')
Bootstrap(app)
db = SQLAlchemy(app)
