import logging
import logging.handlers
import logging.config
import os
import yaml


if not os.path.exists('logs'):
    os.makedirs('logs')


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
API_URL_FLASK = os.getenv('POSTGREST_FLASK_HOST', 'postgrest:3000')


def get_logger(path='webapp/configs/logging.yaml'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger('artemis_logger')
        log.info('Loaded configuration from {}'.format(path))
    else:
        FORMAT = '%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s'
        logging.basicConfig(format=FORMAT, level=logging.INFO)
        log = logging
        log.info('Loaded default configuration')
    return log

def flatten(items, seqtypes=(list, tuple)):
    if not isinstance(items, seqtypes):
        return [items]
    for i in range(len(items)):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i + 1] = items[i]
    return items