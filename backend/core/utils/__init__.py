import os
import logging
import logging.handlers
import logging.config
import yaml
from logging.handlers import SMTPHandler
import pickle
import hashlib


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
    return hashlib.shake_128(pickle.dumps(
        [prefix, hijack_as, _type])).hexdigest(16)


def purge_redis_eph_pers_keys(redis_instance, ephemeral_key, persistent_key):
    redis_pipeline = redis_instance.pipeline()
    # purge also tokens since they are not relevant any more
    redis_pipeline.delete('{}token_active'.format(ephemeral_key))
    redis_pipeline.delete('{}token'.format(ephemeral_key))
    redis_pipeline.delete(ephemeral_key)
    redis_pipeline.srem('persistent-keys', persistent_key)
    redis_pipeline.execute()
