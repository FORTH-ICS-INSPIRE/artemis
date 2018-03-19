import sys
import os
from socketIO_client import SocketIO
import ipaddress
import grpc
import argparse

# to import protogrpc, since the root package has '-'
# in the name ("artemis-tool")
this_script_path = os.path.realpath(__file__)
upper_dir = '/'.join(this_script_path.split('/')[:-2])
sys.path.insert(0, upper_dir)
from protogrpc import service_pb2, service_pb2_grpc


class ExaBGP():

    def __init__(self, prefixes, address, port):
        self.config = {}
        self.config['host'] = str(address) + ":" + str(port)
        self.config['prefixes'] = prefixes
        self.flag = True
        self.channel = grpc.insecure_channel('localhost:50051')
        self.stub = service_pb2_grpc.MessageListenerStub(self.channel)

    def start_loop(self):
        while(self.flag):
            self.start()

    def start(self):
        socketIO = SocketIO("http://" + str(self.config['host']))
        print("[ExaBGP] %s monitor service is up for prefixes %s" %
              (self.config['host'],  self.config['prefixes']))

        def on_connect(*args):
            prefixes_ = {"prefixes": self.config['prefixes']}
            socketIO.emit("exa_subscribe", prefixes_)

        def on_pong(*args):
            socketIO.emit("ping")

        def exabgp_msg(bgp_message):
            self.stub.queryMformat(service_pb2.MformatMessage(
                type=bgp_message['type'],
                timestamp=bgp_message['timestamp'],
                as_path=bgp_message['path'],
                service='ExaBGP {}'.format(self.config['host']),
                prefix=bgp_message['prefix']
            ))

        # not used yet (TODO)
        def on_reconnecting():
            print("ExaBGP host ", self.config['host'], " reconnecting.")

        # not used yet (TODO)
        def on_reconnect_error():
            print("ExaBGP host ", self.config['host'], " reconnect error.")

        def on_disconnect():
            print("ExaBGP host ", self.config['host'], " disconnected.")
            socketIO.close()

        # not used yet (TODO)
        def on_error():
            print("ExaBGP host ", self.config['host'], " error.")

        socketIO.on("connect", on_connect)
        socketIO.on("disconnect", on_disconnect)
        socketIO.on("pong", on_pong)
        socketIO.on("exa_message", exabgp_msg)
        #socketIO.on("reconnecting", on_reconnecting)
        #socketIO.on("reconnect_error", on_reconnect_error)
        #socketIO.on("error", on_error)

        socketIO.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ExaBGP Monitor Client')
    parser.add_argument('-p', '--prefix', type=str, dest='prefix', default=None,
                        help='Prefix to be monitored')
    parser.add_argument('-r', '--host', type=str, dest='host', default=None,
                        help='Prefix to be monitored')

    args = parser.parse_args()

    prefixes = args.prefix.split(',')
    (address, port) = args.host.split(':')
    exa = ExaBGP(prefixes, address, port)
    exa.start()
