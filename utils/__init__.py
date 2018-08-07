import logging
import logging.config
import json
import os

if not os.path.exists('logs'):
    os.makedirs('logs')

if os.path.exists('configs/logging.json'):
    with open('configs/logging.json', 'r') as f:
        config = json.load(f)
        logging.config.dictConfig(config)

log = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')

def flatten(items, seqtypes=(list, tuple)):
    if not isinstance(items, seqtypes):
        return [items]
    for i in range(len(items)):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i+1] = items[i]
    return items

class ArtemisError(Exception):
    def __init__(self, _type, _where):
        self.type = _type
        self.where = _where

        message = 'type: {}, at: {}'.format(_type, _where)

        # Call the base class constructor with the parameters it needs
        super().__init__(message)

def exception_handler(f):
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            log.error('Exception', exc_info=True)
            return True
    return wrapper
