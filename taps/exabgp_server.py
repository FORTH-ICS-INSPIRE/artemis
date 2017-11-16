#!/usr/bin/env python

import time
import socketio
from flask import Flask, abort
from sys import stdin, stdout, stderr
import json
import time
import sys
from netaddr import IPNetwork, IPAddress
import radix

async_mode = 'threading'
sio = socketio.Server(logger=False, async_mode=async_mode)
app = Flask(__name__)
thread = None
clients = {}
global hostname
hostname = 'exabgp'


def message_parser(line):
    global hostname
    try:
        temp_message = json.loads(line)
        if temp_message['type'] == 'update':
            for origin in temp_message['neighbor']['message']['update']['announce']['ipv4 unicast']:
                message = {
                    'type': 'A',
                    'timestamp': temp_message['time'],
                    'peer': temp_message['neighbor']['ip'],
                    'host': hostname,
                    'path': temp_message['neighbor']['message']['update']['attribute']['as-path'],
                }
                for prefix in temp_message['neighbor']['message']['update']['announce']['ipv4 unicast'][origin]:
                    message['prefix'] = prefix
                    for sid in clients.keys():
                        try:
                            if clients[sid][0].search_worst(prefix) is not None:
                                stderr.write('Sending exa_message to ' + str(clients[sid][0]) + '\n')
                                sio.emit(
                                    'exa_message', message, room=sid)
                        except:
                            print('Invalid format received from %s' % str(sid))
    except Exception as e:
        stderr.write(str(e) + '\n')


def exabgp_update_event():
    while True:
        line = stdin.readline().strip()
        messages = message_parser(line)


@app.route('/')
def index():
    abort(404)


@sio.on('connect')
def artemis_connect(sid, environ):
    global thread
    if thread is None:
        thread = sio.start_background_task(exabgp_update_event)
    sio.emit("connect")

@sio.on('disconnect')
def artemis_disconnect(sid):
    if sid in clients:
        del clients[sid]


@sio.on('exa_subscribe')
def artemis_exa_subscribe(sid, message):
    prefixes_tree = radix.Radix()

    try:
        for prefix in message['prefixes']:
            prefixes_tree.add(prefix)

        clients[sid] = [prefixes_tree, True]

    except:
        stderr.write('Invalid format received from %s\n' % str(sid))

if __name__ == '__main__':
    hostname = sys.argv[1]
    app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
    app.config['SECRET_KEY'] = 'secret!'

    app.run(host='0.0.0.0', threaded=True)
