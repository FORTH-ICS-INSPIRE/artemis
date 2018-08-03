import pika
from functools import wraps, partial
from multiprocessing import Process
from time import sleep
import inspect


def consumer_callback(exchange, exchange_type, routing_key):
    def decorator(func):
        def process_func(self):
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            channel = connection.channel()
            channel.exchange_declare(exchange=exchange,
                    exchange_type=exchange_type)
            result = channel.queue_declare(exclusive=True)
            queue = result.method.queue
            channel.queue_bind(exchange=exchange,
                    queue=queue,
                    routing_key=routing_key)
            t_func = partial(func, self)
            channel.basic_consume(t_func,
                    queue=queue,
                    no_ack=True)
            channel.start_consuming()

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            p = Process(target=process_func, args=(self,))
            return p

        return wrapper
    return decorator

# @consumer_callback('bgp_update', 'direct', 'update')
# def lol(channel, method, header, body):
#     print(body)
#
# p = lol()
# print('{}:{}'.format(p, type(p)))
# p.start()
# sleep(5)
# p.terminate()
