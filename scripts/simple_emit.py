from kombu import Connection

#: Create connection
#: If hostname, userid, password and virtual_host is not specified
#: the values below are the default, but listed here so it can
#: be easily changed.
with Connection('amqp://guest:guest@localhost:5672//') as conn:

    #: SimpleQueue mimics the interface of the Python Queue module.
    #: First argument can either be a queue name or a kombu.Queue object.
    #: If a name, then the queue will be declared with the name as the queue
    #: name, exchange name and routing key.
    with conn.SimpleQueue('modules_control') as queue:
        queue.put({
            'module': 'monitor_',
            'action': 'start'
            },
            serializer='json',
            compression='zlib'
            )

