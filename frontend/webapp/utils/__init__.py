import logging
import json
import os
import time

SYSLOG_HOST, SYSLOG_PORT = os.getenv('SYSLOG_HOST', 'localhost:514').split(':')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')

def get_logger():
    log = logging.getLogger('artemis_logger')
    log.setLevel(logging.DEBUG)
    handler = logging.handlers.SysLogHandler(address=(SYSLOG_HOST, int(SYSLOG_PORT)))
    formatter = logging.Formatter('%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log

# https://stackoverflow.com/questions/16136979/set-class-with-timed-auto-remove-of-elements
class TimedSet(set):
    def __init__(self):
        self.__table = {}

    def add(self, item, timeout=10):
        self.__table[item] = time.time() + timeout
        set.add(self, item)

    def __contains__(self, item):
        return time.time() < self.__table.get(item, -1)

    def __iter__(self):
        for item in set.__iter__(self):
            if time.time() < self.__table.get(item):
                yield item

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
