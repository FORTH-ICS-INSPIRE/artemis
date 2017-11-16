from socketIO_client import SocketIO
from core.files import WriteLogs
import time
import sys


class RIPEris:

    ris_conf = {'host_ip': "http://stream-dev.ris.ripe.net/stream", 'host_port': 80}
    
    config = {'origin': None, 'type': None, 'moreSpecific': None, 'lessSpecific': None, 
            'peer': None, 'selector': 'message', 'rateLimit': '100000' }

    def __init__(self, prefix, host, raw_log_queue):

        self.config['host'] = host
        self.config['prefix'] = prefix

        self.write2file = WriteLogs('RIPEris', host, prefix)

        self.raw_log_queue = raw_log_queue
        self.start_loop()


    def start_loop(self):
        while(True):
            self.start()


    def start(self):

        socketIO = SocketIO(self.ris_conf['host_ip'], self.ris_conf['host_port'])       
        print("[RIPE] %s monitor service is up for prefix %s" % (self.config['host'],  self.config['prefix']))

        
        def on_disconnect():
            print("RIPEris collector %s with prefix %s has been disconnected." % (self.config['host'], self.config['prefix']))
            socketIO.close()
        
        def on_connect(*args):
            socketIO.emit("ping")
            socketIO.emit("ris_subscribe", self.config)

        def on_pong(*args):
            socketIO.emit("ping")

        def ris_message(bgp_message):

            # Write raw log
            self.write2file.append_log(bgp_message)

            # Put in queue to be tranformed to Pformat
            self.raw_log_queue.put(('RIPEris', self.config['host'], bgp_message))
            
            socketIO.emit("ping")

        def on_reconnecting():
            print("RIPEris host ", self.config['host'], " reconnecting.")


        def on_reconnect_error():
            socketIO.emit("ping")
            socketIO.emit("ris_subscribe", self.config)


        def on_error():
            print("Error with RIPEris collector %s with prefix %s" % (self.config['host'], self.config['prefix']))
            
        socketIO.on("connect", on_connect)
        socketIO.on("pong", on_pong)
        socketIO.on("ris_message", ris_message)
        socketIO.on("disconnect", on_disconnect)
        socketIO.on("reconnecting", on_reconnecting)
        socketIO.on("reconnect_error", on_reconnect_error)
        socketIO.on("error", on_error)

        socketIO.wait()


    def get_config_parameter(self, name):
        return self.config[name]

