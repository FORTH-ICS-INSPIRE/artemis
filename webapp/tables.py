from flask_table import Table, Col
from flask import url_for


class MonitorTable(Table):
    table_id = 'table'
    classes = ['table table-striped']
    no_items = 'Logs are empty..'
    id = Col('ID')
    prefix = Col('Prefix')
    origin_as = Col('Origin AS')
    as_path = Col('AS Path')
    service = Col('Service')
    type = Col('Type')
    timestamp = Col('Timestamp')
    hijack_id = Col('Hijack ID')
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
    num_peers = Col('Num of peers')
    num_asns_inf = Col('Num of ASNs inf')
    time_started = Col('Time Started')
    time_last = Col('Time Last')
    time_ended = Col('Time Ended')
    allow_sort = True

    def sort_url(self, col_key, reverse=False):
        if reverse:
            direction = 'desc'
        else:
            direction = 'asc'
        return url_for('show_hijacks', sort=col_key, direction=direction)
