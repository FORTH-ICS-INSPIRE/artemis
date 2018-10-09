import os
import time
import logging
import logging.handlers
import logging.config
import yaml
from logging.handlers import SMTPHandler


# if not os.path.exists('snapshots'):
#     os.makedirs('snapshots')


if not os.path.exists('logs'):
    os.makedirs('logs')


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
MEMCACHED_HOST = os.getenv('MEMCACHED_HOST', 'localhost')


def get_logger(path='configs/logging.yaml'):
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
    def __init__(self, timeout=10):
        self.__table = {}
        self.timeout = timeout

    def add(self, item):
        self.__table[item] = time.time() + self.timeout
        set.add(self, item)

    def __contains__(self, item):
        if time.time() < self.__table.get(item, -1):
            self.__table[item] = time.time() + self.timeout
            return True
        return False

    def __iter__(self):
        for item in set.__iter__(self):
            if time.time() < self.__table.get(item):
                yield item


def flatten(items, seqtypes=(list, tuple)):
    if not isinstance(items, seqtypes):
        return [items]
    for i in range(len(items)):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i + 1] = items[i]
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
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (self.fromaddr, ", ".join(self.toaddrs), self.getSubject(record), formatdate(), msg)
            if self.username:
                smtp.ehlo()
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

