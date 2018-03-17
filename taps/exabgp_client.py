import sys
from socketIO_client import SocketIO
import ipaddress
from protogrpc import service_pb2, service_pb2_grpc
import grpc


class ExaBGP():

    socketIO = None
    config = {'host': None, 'prefixes': None}

    def __init__(self, prefixes, address_port):
        self.config['host'] = str(address_port[0]) + ":" + str(address_port[1])
        self.config['prefixes'] = prefixes
        self.flag = True
        self.start_loop()

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
            channel = grpc.insecure_channel('localhost:50051')
            stub = service_pb2_grpc.MessageListenerStub(channel)
            stub.queryMformat(service_pb2.MformatMessage(
                type=bgp_message['type'],
                timestamp=bgp_message['timestamp'],
                as_path=bgp_message['path'],
                service='ExaBGP {}'.format(self.config['host']),
                origin_as=bgp_message['peer'],
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

    def stop(self):
        if self.flag:
            self.flag = False
