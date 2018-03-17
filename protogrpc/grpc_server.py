import grpc
from protogrpc import service_pb2
from protogrpc import service_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from webapp.models import Monitor


class GrpcServer():

    def __init__(self, db, monitor_queue):
        self.db = db
        self.db.create_all()
        self.monitor_queue = monitor_queue
        self.server_process = None

    class MonitorGrpc(service_pb2_grpc.MessageListenerServicer):

        def __init__(self, db, monitor_queue):
            self.db = db
            self.monitor_queue = monitor_queue

        def queryMformat(self, request, context):
            msg = protobuf_to_dict(request)
            if msg['type'] == 'A':
                self.monitor_queue.put(msg)
            self.db.session.add(Monitor(msg))
            self.db.session.commit()
            return service_pb2.Empty()

    def start(self, monitor, detector, mitigator=None):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        service_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.db, self.monitor_queue),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')
        _thread.start_new_thread(self.grpc_server.start, ())
        print("GRPC Server Started..")

    def stop(self):
        self.grpc_server.stop(0)
        print("GRPC Server Stopped..")
