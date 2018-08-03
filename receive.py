#!/usr/bin/env python
import functools
import pika
import sys
from pickle import loads
from utils.mq import AsyncConsumer
import threading


def a_func(ch, m, h, b):
    print('hijack_update {}'.format(loads(b)))

def b_func(ch, m, h, b):
    print('handled_update {}'.format(loads(b)))

def main():
    cons_1 = AsyncConsumer(exchange='hijack_update', routing_key='update', cb=a_func)
    cons_2 = AsyncConsumer(exchange='handled_update', routing_key='update', cb=b_func)

    try:
        t1 = threading.Thread(target=cons_1.run, args=())
        t2 = threading.Thread(target=cons_2.run, args=())

        t1.start()
        t2.start()

        t1.join()
        t2.join()
    except KeyboardInterrupt:
        cons_1.stop()
        cons_2.stop()


if __name__ == '__main__':
    main()
