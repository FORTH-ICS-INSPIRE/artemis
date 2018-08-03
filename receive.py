#!/usr/bin/env python
import pika
import sys
from pickle import loads
from utils.mq import AsyncConsumer

def a_func(ch, m, h, b):
    print('hijack_update {}'.format(loads(b)))

def b_func(ch, m, h, b):
    print('handled_update {}'.format(loads(b)))

def main():
    example = AsyncConsumer(exchange='bgp_update', routing_key='update', cb=a_func)
    try:
        example.run()
    except KeyboardInterrupt:
        example.stop()


if __name__ == '__main__':
    main()
