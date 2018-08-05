#!/usr/bin/env python
import functools
import pika
import sys
from pickle import loads
from utils.mq import AsyncConnection


def a_func(ch, m, h, b):
    print('{}'.format(loads(b)))


def main():
    t1 = AsyncConnection(exchange='bgp_update', routing_key='update', cb=a_func, objtype='consumer')

    try:
        t1.start()
        t1.join()
    except KeyboardInterrupt:
        t1.stop()

if __name__ == '__main__':
    main()
