import os
import logging
from flask_compress import Compress
from flask_security import Security, SQLAlchemyUserDatastore
from webapp.data.models import db, Role, User


class BaseConfig(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOGGING_LOCATION = 'webapp.log'
    LOGGING_LEVEL = logging.DEBUG
    SECURITY_PASSWORD_SALT = b'O\xdb\xd4\x16\xb8\xcaND6\xe8q\xe5'
    CACHE_TYPE = 'simple'
    COMPRESS_MIMETYPES = ['text/html', 'text/css', 'text/xml',
                          'application/json', 'application/javascript']
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    SUPPORTED_LANGUAGES = {'en': 'English'}
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    ENV = 'dev'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SECRET_KEY = b':\xce!\x8ec\xaa\xa2T\xf2W\xa4F=\xb3\xd9\xb6D\xc3\x8a\x9b\xd5h\x85\x06'


class StagingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    ENV = 'staging'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SECRET_KEY = b'\xad\xf3o\xe3\x00\xd6-<3\xee\xcd\x9e\x9c8[\x83#\xab\x05\xaaM\x8f5\xd6'


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    ENV = 'prod'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../db/artemis.db'
    SECRET_KEY = b"\xfd'\xabW\xe7X$\xa8\xfd\xb3M\x84:$\xd3a\xa6\xbb`\x8b\xaa\xb9\x15r"


config = {
    'dev': 'webapp.config.DevelopmentConfig',
    'staging': 'webapp.config.StagingConfig',
    'prod': 'webapp.config.ProductionConfig',
    'default': 'webapp.config.DevelopmentConfig'
}


def configure_app(app):
    config_name = os.getenv('FLASK_CONFIGURATION', 'default')
    app.config.from_object(config[config_name])
    app.config.from_pyfile('webapp.cfg', silent=True)
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
