import logging
import json
import os
import time

SYSLOG_HOST, SYSLOG_PORT = os.getenv('SYSLOG_HOST', 'localhost:514').split(':')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
API_URL_FLASK = os.getenv('POSTGREST_FLASK_HOST', 'postgrest:3000')
API_URL_CLIENT = os.getenv('POSTGREST_CLIENT_HOST', 'localhost:12000')

def get_logger():
    log = logging.getLogger('webapp_logger')
    log.setLevel(logging.DEBUG)
    handler = logging.handlers.SysLogHandler(address=(SYSLOG_HOST, int(SYSLOG_PORT)))
    formatter = logging.Formatter('%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log
