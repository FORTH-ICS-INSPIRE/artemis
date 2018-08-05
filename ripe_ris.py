from socketIO_client_nexus import SocketIO
from kombu import Connection, Producer, Exchange, Queue
import traceback

connection = Connection('amqp://guest:guest@localhost:5672//')
exchange = Exchange('bgp_update', type='direct', durable=False)
queue = Queue('bgp_queue', exchange, routing_key='updates')

msg_num = 1

def on_rrc_msg(msg):
    print(msg)

def on_ris_msg(msg):
    global msg_num
    try:
        producer = Producer(connection)
        producer.publish(
            msg,
            exchange=queue.exchange,
            routing_key=queue.routing_key,
            serializer='json')
        print('Published #{}'.format(msg_num))
        msg_num += 1
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
    socket_io.disconnect()
