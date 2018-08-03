import pika
from functools import wraps, partial
from multiprocessing import Process
from time import sleep
import inspect
from utils.mq import AsyncConsumer


def consumer_callback(exchange, exchange_type, routing_key):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            t_func = partial(func, self)
            consumer = AsyncConsumer(exchange=exchange,
                    exchange_type=exchange_type,
                    routing_key=routing_key,
                    cb=t_func)
            return consumer
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
