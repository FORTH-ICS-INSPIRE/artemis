import logging
import logging.handlers
import logging.config
import os
import yaml


SYSLOG_HOST, SYSLOG_PORT = os.getenv('SYSLOG_HOST', 'localhost:514').split(':')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
API_URL_FLASK = os.getenv('POSTGREST_FLASK_HOST', 'postgrest:3000')


def get_logger(path='configs/logging.yaml'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger('artemis_logger')
        log.info('Loaded configuration from {}'.format(path))
    else:
        log = logging.getLogger('artemis_logger')
        log.setLevel(logging.DEBUG)
        handler = logging.handlers.SysLogHandler(
            address=(SYSLOG_HOST, int(SYSLOG_PORT)))
        formatter = logging.Formatter(
            '%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s')
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.info('Loaded default configuration')
    return log
