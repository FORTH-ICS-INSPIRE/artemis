#!/usr/bin/python
import argparse
import logging
import time
from sys import stderr
from sys import stdout

import socketio
from flask import Flask


log = logging.getLogger("artemis")
log.setLevel(logging.DEBUG)
# create a file handler
handler = logging.FileHandler("/tmp/server.log")
handler.setLevel(logging.DEBUG)
# create a logging format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
# add the handlers to the logger
log.addHandler(handler)

wz_log = logging.getLogger("werkzeug")
wz_log.setLevel(logging.ERROR)

async_mode = "threading"
sio = socketio.Server(logger=False, async_mode=async_mode)
app = Flask(__name__)
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
app.config["SECRET_KEY"] = "secret!"

clients = set()
hostname = ""
thread = None


@sio.on("connect")
def artemis_connect(sid, environ):
    log.info("connect {}".format(sid))
    clients.add(sid)


@sio.on("disconnect")
def artemis_disconnect(sid):
    log.info("disconnect {}".format(sid))
    if sid in clients:
        clients.remove(sid)


@sio.on("route_command")
def route_command(sid, message):
    log.info("route_command '{}' from {}".format(message["command"], sid))
    stderr.write(message["command"] + "\n")
    stderr.flush()
    stdout.write(message["command"] + "\n")
    stdout.flush()
    time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ExaBGP Route Command Server")
    parser.add_argument(
        "--ssl", dest="ssl", default=False, help="Flag to use SSL", action="store_true"
    )
    args = parser.parse_args()

    ssl = args.ssl

    if ssl:
        log.info("Starting Socket.io SSL server..")
        app.run(ssl_context="adhoc", host="0.0.0.0")
    else:
        log.info("Starting Socket.io server..")
        app.run(host="0.0.0.0")
