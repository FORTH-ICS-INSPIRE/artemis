import logging
import logging.handlers
import logging.config
import os
import yaml


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
API_URL_FLASK = os.getenv('POSTGREST_FLASK_HOST', 'postgrest:3000')
SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'localhost')
SUPERVISOR_PORT = os.getenv('SUPERVISOR_PORT', 9001)


def get_logger(path='/etc/artemis/logging.yaml'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger('webapp_logger')
        log.info('Loaded configuration from {}'.format(path))
    else:
        FORMAT = '%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s'
        logging.basicConfig(format=FORMAT, level=logging.INFO)
        log = logging
        log.info('Loaded default configuration')
    return log


def flatten(items, seqtypes=(list, tuple)):
    res = []
    if not isinstance(items, seqtypes):
        return [items]
    for item in items:
        if isinstance(item, seqtypes):
            res += flatten(item)
        else:
            res.append(item)
    return res
