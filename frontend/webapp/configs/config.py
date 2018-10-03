import os
import logging
from flask_compress import Compress
from flask_security import Security, SQLAlchemyUserDatastore
from webapp.data.models import db, Role, User
from webapp.templates.forms import ExtendedRegisterForm, ExtendedLoginForm

log = logging.getLogger('webapp_logger')


class BaseConfig(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = True
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

    DEBUG = True
    TESTING = True
    LOGGING_LEVEL = logging.INFO

    SECURITY_REGISTERABLE = True
    SECURITY_REGISTER_URL = "/create_account"

    SECRET_KEY = b"\xfd'\xabW\xe7X$\xa8\xfd\xb3M\x84:$\xd3a\xa6\xbb`\x8b\xaa\xb9\x15r"


class ProductionConfig(BaseConfig):
    if not os.path.exists('/etc/webapp/db'):
        os.makedirs('/etc/webapp/db')

    DB_NAME = "artemis_webapp.db"
    DB_FULL_PATH = "/etc/webapp/db/" + DB_NAME
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_FULL_PATH

    SECURITY_USER_IDENTITY_ATTRIBUTES = ('username', 'email')
    SECURITY_SEND_REGISTER_EMAIL = False
    SECURITY_RECOVERABLE = False
    LOGGING_LEVEL = logging.INFO
    WEBAPP_HOST = '0.0.0.0'
    WEBAPP_PORT = int(os.getenv('FLASK_PORT', '8000'))

    SECRET_KEY = b"\xfd'\xabW\xe7X$\xa8\xfd\xb3M\x84:$\xd3a\xa6\xbb`\x8b\xaa\xb9\x15r"


config = {
    'default': 'webapp.config.ProductionConfig'
}


def configure_app(app):
    app.config.from_object('webapp.configs.config.ProductionConfig')
    log.info('Loading default configuration..')

    log.info('Reading additional configuration from webapp.cfg..')
    app.config.from_pyfile('configs/webapp.cfg', silent=False)

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
