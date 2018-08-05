from socketIO_client_nexus import SocketIO
import pickle
from utils.mq import AsyncConnection

publisher = AsyncConnection(exchange='bgp_update',
        objtype='publisher',
        routing_key='update',
        exchange_type='direct')

publisher.start()

def on_rrc_msg(msg):
    print(msg)

def on_ris_msg(msg):
    try:
        publisher.publish_message(msg)
    except Exception:
        traceback.print_exc()

try:
    socket_io = SocketIO('http://stream-dev.ris.ripe.net/stream', wait_for_connection=False)
    socket_io.on('ris_rrc_list', on_rrc_msg)
    socket_io.on('ris_message', on_ris_msg)

    socket_io.emit('ris_subscribe', '{"hosts":"rrc01"}')
    socket_io.wait()
except Exception:
    import sys
    sys.stdout.flush()
    traceback.print_exc()
    log.warning('RIPE RIS server is down. Try again later..')
    publisher.stop()
    socket_io.disconnect()
