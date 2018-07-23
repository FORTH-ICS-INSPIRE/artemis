#!/usr/bin/python

import sys
from sys import stdin, stdout, stderr
from flask import Flask, abort
import socketio
import json
import logging
import radix

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
async_mode = 'threading'
sio = socketio.Server(logger=False, async_mode=async_mode)
app = Flask(__name__)
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
app.config['SECRET_KEY'] = 'secret!'
thread = None
clients = {}
hostname = 'exabgp'


def message_parser(line):
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
                    for sid in clients:
                        if clients[sid][0].search_best(prefix):
                            print('Sending to {} for {}'.format(sid, prefix))
                            # sio.emit('exa_message', message, room=sid)
    except:
        pass


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
    sio.emit('connect')


@sio.on('disconnect')
def artemis_disconnect(sid):
    if sid in clients:
        del clients[sid]


@sio.on('ping')
def artemis_ping(sid):
    sio.emit('pong', room=sid)


@sio.on('exa_subscribe')
def artemis_exa_subscribe(sid, message):
    all_prefixes = []
    try:
        prefix_tree = radix.Radix()
        for prefix in message['prefixes']:
            prefix_tree.add(prefix)
        clients[sid] = (prefx_tree, True)
    except:
        print('Invalid format received from %s'.format(str(sid)))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        hostname = sys.argv[1]
    app.run(host='0.0.0.0', threaded=True)
