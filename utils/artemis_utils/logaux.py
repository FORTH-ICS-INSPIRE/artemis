# aux logging functions
from logging.handlers import SMTPHandler

from artemis_utils.envvars import ARTEMIS_WEB_HOST
from artemis_utils.envvars import HIJACK_LOG_FIELDS

from . import log


class TLSSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.starttls()  # for tls add this line
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class SSLSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


def hijack_log_field_formatter(hijack_dict):
    logged_hijack_dict = {}
    try:
        fields_to_log = set(hijack_dict.keys()).intersection(HIJACK_LOG_FIELDS)
        for field in fields_to_log:
            logged_hijack_dict[field] = hijack_dict[field]
        # instead of storing in redis, simply add the hijack url upon logging
        if "hijack_url" in HIJACK_LOG_FIELDS and "key" in hijack_dict:
            logged_hijack_dict["hijack_url"] = "https://{}/main/hijack?key={}".format(
                ARTEMIS_WEB_HOST, hijack_dict["key"]
            )
    except Exception:
        log.exception("exception")
        return hijack_dict
    return logged_hijack_dict
