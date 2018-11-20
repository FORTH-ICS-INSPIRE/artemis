import os
import time
import logging
import logging.handlers
import logging.config
import yaml
from logging.handlers import SMTPHandler
import pickle
import hashlib
import threading


# if not os.path.exists('snapshots'):
#     os.makedirs('snapshots')


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'localhost')
SUPERVISOR_PORT = os.getenv('SUPERVISOR_PORT', 9001)


def get_logger(path='/etc/artemis/logging.yaml'):
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


# https://stackoverflow.com/questions/16136979/set-class-with-timed-auto-remove-of-elements


class TimedSet(set):

    def __init__(self, timeout=60*60*24):
        self.__table = {}
        self.timeout = timeout
        self.timers = {}

    def add(self, item):
        set.add(self, item)
        self.timers[item] = threading.Timer(self.timeout, self._remove, args=(item,))
        self.timers[item].start()

    def _remove(self, item):
        set.discard(self, item)

    def __contains__(self, item):
        if item in set(self):
            self.timers[item].cancel()
            self.timers[item] = threading.Timer(self.timeout, self._remove, args=(item,))
            self.timers[item].start()
            return True
        return False


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
            except Exception:
                log.exception('exception')
                return True
        return wrapper
    return function_wrapper


class SMTPSHandler(SMTPHandler):

    def emit(self, record):
        """
        Overwrite the logging.handlers.SMTPHandler.emit function with SMTP_SSL.
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib
            from email.utils import formatdate
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP_SSL(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ", ".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg)
            if self.username:
                smtp.ehlo()
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


def redis_key(prefix, hijack_as, _type):
    assert(isinstance(prefix, str))
    assert(isinstance(hijack_as, int))
    assert(isinstance(_type, str))
    return hashlib.md5(pickle.dumps([prefix, hijack_as, _type])).hexdigest()
