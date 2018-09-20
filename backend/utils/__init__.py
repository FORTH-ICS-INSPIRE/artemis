import json
import os
import time
import logging

if not os.path.exists('snapshots'):
    os.makedirs('snapshots')

SYSLOG_HOST = os.getenv('SYSLOG_HOST', 'localhost')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
MEMCACHED_HOST = os.getenv('MEMCACHED_HOST', 'localhost')


def get_logger(name):
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    handler = logging.handlers.SysLogHandler(address= (SYSLOG_HOST,514))
    formatter = logging.Formatter('%(module)s @ %(funcName)s: %(message)s')
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

def exception_handler(log):
    def function_wrapper(f):
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                log.exception('exception')
                return True
        return wrapper
    return function_wrapper
