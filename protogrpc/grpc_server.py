import grpc
from protogrpc import mservice_pb2
from protogrpc import mservice_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from utils import log
import pika
import json


class GrpcServer():


    def __init__(self):
        self.server_process = None
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))


    class MonitorGrpc(mservice_pb2_grpc.MessageListenerServicer):


        def __init__(self, connection):
            self.channel = connection.channel()
            self.channel.exchange_declare(exchange='bgp_update',
                            exchange_type='direct')


        def queryMformat(self, request, context):
            monitor_event = protobuf_to_dict(request)
            self.channel.basic_publish(exchange='bgp_update',
                                routing_key='#',
                                body=json.dumps(monitor_event))
            return mservice_pb2.Empty()


    def start(self):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        mservice_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.connection),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')
        _thread.start_new_thread(self.grpc_server.start, ())
        log.info('GRPC Server Started..')


    def stop(self):
        self.grpc_server.stop(0)
        log.info('GRPC Server Stopped..')

