import os
import logging
from flask_compress import Compress
from flask_security import Security, SQLAlchemyUserDatastore
from webapp.data.models import db, Role, User

log = logging.getLogger('artemis_logger')

class BaseConfig(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOGGING_LOCATION = 'logs/webapp.log'
    SECURITY_PASSWORD_SALT = b'O\xdb\xd4\x16\xb8\xcaND6\xe8q\xe5'
    CACHE_TYPE = 'simple'
    COMPRESS_MIMETYPES = ['text/html', 'text/css', 'text/xml',
                          'application/json', 'application/javascript']
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    SUPPORTED_LANGUAGES = {'en': 'English'}
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    SECURITY_TRACKABLE = True
    POSTS_PER_PAGE = 25

    DEBUG = False
    TESTING = False
    LOGGING_LEVEL = logging.INFO
    SECRET_KEY = b':\xce!\x8ec\xaa\xa2T\xf2W\xa4F=\xb3\xd9\xb6D\xc3\x8a\x9b\xd5h\x85\x06'

class ProductionConfig(BaseConfig):
    DEBUG = True
    TESTING = True
    ENV = 'prod'

    if not os.path.exists('db'):
        os.makedirs('db')

    LOGGING_LEVEL = logging.INFO
    WEBAPP_HOST = '0.0.0.0'
    WEBAPP_PORT = 8000

    SQLALCHEMY_DATABASE_URI = 'sqlite:////root/db/artemis.db'
    SECRET_KEY = b"\xfd'\xabW\xe7X$\xa8\xfd\xb3M\x84:$\xd3a\xa6\xbb`\x8b\xaa\xb9\x15r"
    SECURITY_TRACKABLE = True
    POSTS_PER_PAGE = 25
    VERSION = "0.0.0"


config = {
    'default': 'webapp.config.ProductionConfig'
}

def configure_app(app):
    app.config.from_object('webapp.configs.config.ProductionConfig')
    log.info('Loading default configuration..')
    
    log.info('Reading additional configuration from webapp.cfg..')
    app.config.from_pyfile('configs/webapp.cfg', silent=False)

    # Configure logging
    handler = logging.FileHandler(app.config['LOGGING_LOCATION'])
    handler.setLevel(app.config['LOGGING_LEVEL'])
    formatter = logging.Formatter(app.config['LOGGING_FORMAT'])
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    # Configure Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    app.security = Security(app, user_datastore)
    # Configure Compressing
    Compress(app)
