from webapp.shared import babel
from babel.dates import format_datetime
from flask_table import Table, Col, DatetimeCol, BoolCol, ButtonCol
from flask import url_for


class CustomDatetimeCol(Col):
    """Format the content as a datetime, unless it is None, in which case,
    output empty.
    """
    def __init__(self, name, datetime_format='short', **kwargs):
        super(CustomDatetimeCol, self).__init__(name, **kwargs)
        self.datetime_format = datetime_format

    def td_format(self, content):
        if content:
            return format_datetime(content,
                                   self.datetime_format,
                                   tzinfo=babel.default_timezone,
                                   locale=babel.default_locale)
        else:
            return ''


class MonitorTable(Table):
    table_id = 'table'
    classes = ['table table-striped']
    no_items = 'Logs are empty..'
    id = Col('ID')
    prefix = Col('Prefix')
    origin_as = Col('Origin AS')
    peer_as = Col('Peer AS')
    as_path = Col('AS Path')
    service = Col('Service')
    type = Col('Type')
    timestamp = CustomDatetimeCol('Timestamp')
    hijack_id = Col('Hijack ID')
    handled = BoolCol('Handled')
    allow_sort = True

    def sort_url(self, col_key, reverse=False):
        if reverse:
            direction = 'desc'
        else:
            direction = 'asc'
        return url_for('show_monitors', sort=col_key, direction=direction)


class HijackTable(Table):
    table_id = 'table'
    classes = ['table table-striped']
    no_items = 'Logs are empty..'
    id = Col('ID')
    type = Col('Type')
    prefix = Col('Prefix')
    hijack_as = Col('Hijack AS')
    num_peers_seen = Col('CNum Peers Seen')
    num_asns_inf = Col('CNum ASNs Infected')
    time_started = CustomDatetimeCol('Time Started')
    time_last = CustomDatetimeCol('Time Last Updated')
    time_ended = CustomDatetimeCol('Time Ended')
    to_mitigate = Col('Mit Pending')
    mitigation_started = CustomDatetimeCol('Mit Started')
    mitigate = ButtonCol('Mitigate', 'mitigate_hijack', url_kwargs=dict(id='id'))
    resolved = ButtonCol('Resolved', 'resolved_hijack', url_kwargs=dict(id='id'))
    allow_sort = True

    def sort_url(self, col_key, reverse=False):
        if reverse:
            direction = 'desc'
        else:
            direction = 'asc'
        return url_for('show_hijacks', sort=col_key, direction=direction)
