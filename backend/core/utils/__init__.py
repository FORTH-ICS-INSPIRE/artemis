import os
import logging
import logging.handlers
import logging.config
import yaml
from logging.handlers import SMTPHandler
import pickle
import hashlib
from contextlib import contextmanager
from ipaddress import ip_network as str2ip
import re


RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'localhost')
SUPERVISOR_PORT = os.getenv('SUPERVISOR_PORT', 9001)
DB_NAME = os.getenv('DATABASE_NAME', 'artemis_db')
DB_USER = os.getenv('DATABASE_USER', 'artemis_user')
DB_HOST = os.getenv('DATABASE_HOST', 'postgres')
DB_PASSWORD = os.getenv('DATABASE_PASSWORD', 'Art3m1s')


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


log = get_logger()


@contextmanager
def get_ro_cursor(conn):
    with conn.cursor() as curr:
        try:
            yield curr
        except Exception:
            raise


@contextmanager
def get_wo_cursor(conn):
    with conn.cursor() as curr:
        try:
            yield curr
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


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


def translate_rfc2622(input_prefix):
    """

    :param input_prefix: (str) input IPv4/IPv6 prefix that should be translated according to RFC2622
    :return: output_prefixes: (list of str) output IPv4/IPv6 prefixes
    """
    def valid_prefix(input_prefix):
        try:
            str2ip(input_prefix)
        except Exception:
            return False
        return True

    def calculate_more_specifics(prefix, min_length, max_length):
        prefix_list = []
        for prefix_length in range(min_length, max_length+1):
            prefix_list.extend(prefix.subnets(new_prefix=prefix_length))
        return prefix_list

    # ^- is the exclusive more specifics operator; it stands for the more
    #    specifics of the address prefix excluding the address prefix
    #    itself.  For example, 128.9.0.0/16^- contains all the more
    #    specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
    reg_exclusive = re.match('^(\S*)\^-$', input_prefix)
    if reg_exclusive:
        matched_prefix = reg_exclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen + 1
            max_length = matched_prefix_ip.max_prefixlen
            return list(map(str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)))

    # ^+ is the inclusive more specifics operator; it stands for the more
    #    specifics of the address prefix including the address prefix
    #    itself.  For example, 5.0.0.0/8^+ contains all the more specifics
    #    of 5.0.0.0/8 including 5.0.0.0/8.
    reg_inclusive = re.match('^(\S*)\^\+$', input_prefix)
    if reg_inclusive:
        matched_prefix = reg_inclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen
            max_length = matched_prefix_ip.max_prefixlen
            return list(map(str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)))

    # ^n where n is an integer, stands for all the length n specifics of
    #    the address prefix.  For example, 30.0.0.0/8^16 contains all the
    #    more specifics of 30.0.0.0/8 which are of length 16 such as
    #    30.9.0.0/16.
    reg_n = re.match('^(\S*)\^(\d+)$', input_prefix)
    if reg_n:
        matched_prefix = reg_n.group(1)
        length = int(reg_n.group(2))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = length
            max_length = length
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError('invalid-n-small', input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError('invalid-n-large', input_prefix)
            return list(map(str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)))

    # ^n-m where n and m are integers, stands for all the length n to
    #      length m specifics of the address prefix.  For example,
    #      30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8
    #      which are of length 24 to 32 such as 30.9.9.96/28.
    reg_n_m = re.match('^(\S*)\^(\d+)-(\d+)$', input_prefix)
    if reg_n_m:
        matched_prefix = reg_n_m.group(1)
        min_length = int(reg_n_m.group(2))
        max_length = int(reg_n_m.group(3))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError('invalid-n-small', input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError('invalid-n-large', input_prefix)
            return list(map(str, calculate_more_specifics(matched_prefix_ip, min_length, max_length)))

    return [input_prefix]
