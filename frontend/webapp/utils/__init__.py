import os

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
API_URL_FLASK = os.getenv('POSTGREST_FLASK_HOST', 'postgrest:3000')
SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', 'localhost')
SUPERVISOR_PORT = os.getenv('SUPERVISOR_PORT', 9001)


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
