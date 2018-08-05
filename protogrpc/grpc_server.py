import grpc
from protogrpc import mservice_pb2
from protogrpc import mservice_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from utils import log
from utils.mq import AsyncConnection
import pika
import pickle
import threading
import traceback


class GrpcServer():


    def __init__(self):
        self.server_process = None


    class MonitorGrpc(mservice_pb2_grpc.MessageListenerServicer):


        def __init__(self):
            self.publisher = AsyncConnection(exchange='bgp_update',
                    exchange_type='direct',
                    routing_key='update',
                    objtype='publisher')
            self.publisher.start()


        def queryMformat(self, request, context):
            monitor_event = protobuf_to_dict(request)
            try:
                self.publisher.publish_message(monitor_event)
            except Exception as e:
                print(' [!] exception')
                traceback.print_exc()
            return mservice_pb2.Empty()


    def start(self):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        mservice_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')

        threading.Thread(target=self.grpc_server.start, args=()).start()
        log.info('GRPC Server Started..')


    def stop(self):
        self.grpc_server.stop(0)
        log.info('GRPC Server Stopped..')

