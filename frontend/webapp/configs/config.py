import os
import logging
from flask_compress import Compress
from flask_security import Security, SQLAlchemyUserDatastore
from webapp.data.models import db, Role, User
from webapp.templates.forms import ExtendedRegisterForm, ExtendedLoginForm

log = logging.getLogger('webapp_logger')


class BaseConfig(object):
    if not os.path.exists('/etc/webapp/db'):
        os.makedirs('/etc/webapp/db')

    # SQLALCHEMY
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    DB_NAME = "artemis_webapp.db"
    DB_FULL_PATH = "/etc/webapp/db/" + DB_NAME
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_FULL_PATH

    # LOGGING
    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOGGING_LOCATION = '/var/log/artemis/webapp.log'
    LOGGING_LEVEL = logging.INFO

    # CACHE / COMPRESS
    CACHE_TYPE = 'simple'
    COMPRESS_MIMETYPES = ['text/html', 'text/css', 'text/xml',
                          'application/json', 'application/javascript']
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500

    # BABEL
    SUPPORTED_LANGUAGES = {'en': 'English'}
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'EET'

    # SECURITY
    SECURITY_REGISTERABLE = True
    SECURITY_REGISTER_URL = "/create_account"
    SECURITY_USER_IDENTITY_ATTRIBUTES = ('username', 'email')
    SECURITY_SEND_REGISTER_EMAIL = False
    SECURITY_RECOVERABLE = False
    SECURITY_TRACKABLE = True
    SECURITY_PASSWORD_HASH = 'bcrypt'
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT')

    # JWT
    JWT_TOKEN_LOCATION = ['headers']
    JWT_USER_CLAIMS = 'https://hasura.io/jwt/claims'
    JWT_IDENTITY_CLAIM = 'sub'
    JWT_COOKIE_SECURE = True
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

    # OTHER
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY')

    WEBAPP_HOST = '0.0.0.0'
    WEBAPP_PORT = int(os.getenv('FLASK_PORT', '8000'))
    JS_VERSION = "?=" + os.getenv('JS_VERSION', '0.0.0.1')
    POSTS_PER_PAGE = 25
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


def configure_app(app):
    app.config.from_object('webapp.configs.config.BaseConfig')
    log.info('Loading default configuration..')

    log.info('Reading additional configuration from webapp.cfg..')
    app.config.from_pyfile('/etc/artemis/webapp.cfg', silent=False)

    # Configure logging
    logging_dir = '/'.join(app.config['LOGGING_LOCATION'].split('/')[:-1])
    if logging_dir != '' and not os.path.isdir(logging_dir):
        os.mkdir(logging_dir)
    handler = logging.FileHandler(app.config['LOGGING_LOCATION'])
    handler.setLevel(app.config['LOGGING_LEVEL'])
    formatter = logging.Formatter(app.config['LOGGING_FORMAT'])
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    # Configure Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    app.security = Security(
        app,
        user_datastore,
        register_form=ExtendedRegisterForm,
        login_form=ExtendedLoginForm)

    # Configure Compressing
    Compress(app)
