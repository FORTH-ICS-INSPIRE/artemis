import os
import sys
import time
from xmlrpc.client import ServerProxy

# from multiprocessing import Process

# from kombu import Connection
# from kombu import Exchange
# from kombu import Producer
# from kombu import Queue
# from kombu import uuid

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)

BACKEND_SUPERVISOR_HOST = os.getenv("BACKEND_SUPERVISOR_HOST", "localhost")
BACKEND_SUPERVISOR_PORT = os.getenv("BACKEND_SUPERVISOR_PORT", 9001)
BACKEND_SUPERVISOR_URI = "http://{}:{}/RPC2".format(
    BACKEND_SUPERVISOR_HOST, BACKEND_SUPERVISOR_PORT
)


def wait():
    ctx = ServerProxy(BACKEND_SUPERVISOR_URI)

    try:
        state = ctx.supervisor.getProcessInfo("detection")["state"]
        while state == 10:
            print("[!] Waiting for Detection")
            time.sleep(0.5)
            state = ctx.supervisor.getProcessInfo("detection")["state"]
    except Exception as e:
        print(e)
        sys.exit(-1)
    print("[!] Detection is running")


def send():
    pass


def receive(exchange_name, routing_key):
    pass


if __name__ == "__main__":
    print("[+] Starting")
    wait()
    # TODO
    pass
    print("[+] Exiting")
