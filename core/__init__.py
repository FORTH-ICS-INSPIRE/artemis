__all__ = ['core']

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

class ArtemisError(Exception):
    def __init__(self, _type, _where):
        self.type = _type
        self.where = _where

        message = 'type: {}, at: {}'.format(_type, _where)

        # Call the base class constructor with the parameters it needs
        super().__init__(message)

def exception_handler(f):
    def wrapper(*args):
        try:
            return f(*args)
        except Exception as e:
            log.error(exc_info=True)
            return True
    return wrapper
