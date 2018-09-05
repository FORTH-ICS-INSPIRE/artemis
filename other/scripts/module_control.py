from kombu import Connection
import sys
import os

#: Create connection
#: If hostname, userid, password and virtual_host is not specified
#: the values below are the default, but listed here so it can
#: be easily changed.
with Connection(os.getenv('RABBITMQ_HOST', 'localhost')) as conn:

    #: SimpleQueue mimics the interface of the Python Queue module.
    #: First argument can either be a queue name or a kombu.Queue object.
    #: If a name, then the queue will be declared with the name as the queue
    #: name, exchange name and routing key.
    with conn.SimpleQueue('modules_control') as queue:
        queue.put({
            'module': sys.argv[1],
            'action': sys.argv[2]
            },
            serializer='json',
            compression='zlib'
            )

