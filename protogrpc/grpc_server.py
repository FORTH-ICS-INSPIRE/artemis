import grpc
from protogrpc import mservice_pb2
from protogrpc import mservice_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from utils import log
from utils.mq import AsyncConnection
import pika
import json
import threading


class GrpcServer():


    def __init__(self):
        self.server_process = None
        self.bgp_update_publisher = AsyncConnection(exchange='bgp_update',
                exchange_type='direct',
                routing_key='update',
                objtype='publisher')


    class MonitorGrpc(mservice_pb2_grpc.MessageListenerServicer):


        def __init__(self, publisher):
            self.publisher = publisher


        def queryMformat(self, request, context):
            monitor_event = protobuf_to_dict(request)
            self.publisher.publish_message(monitor_event)
            return mservice_pb2.Empty()


    def start(self):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        threading.Thread(target=self.bgp_update_publisher.run, args=())
        mservice_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.bgp_update_publisher),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')

        threading.Thread(target=self.grpc_server.start, args=())
        log.info('GRPC Server Started..')


    def stop(self):
        self.bgp_update_publisher.stop()
        self.grpc_server.stop(0)
        log.info('GRPC Server Stopped..')

