import grpc
from protogrpc import service_pb2
from protogrpc import service_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from webapp.webapp import WebApplication


class GrpcServer():

    def __init__(self, db, parsed_log_queue):
        self.db = db
        self.db.create_all()
        self.parsed_log_queue = parsed_log_queue

    class MonitorGrpc(service_pb2_grpc.MessageListenerServicer):

        def __init__(self, db, parsed_log_queue):
            self.db = db
            self.parsed_log_queue = parsed_log_queue

        def queryPformat(self, request, context):
            msg = protobuf_to_dict(request)
            self.parsed_log_queue.put(msg)
            self.db.session.add(WebApplication.Monitor(msg))
            self.db.session.commit()
            return service_pb2.Empty()

    class ServiceGrpc(service_pb2_grpc.ServiceListenerServicer):

        def __init__(self, monitor, detector, mitigator):
            self.monitor = monitor
            self.detector = detector
            self.mitigator = mitigator

        def sendServiceHandle(self, request, context):
            msg = protobuf_to_dict(request)
            if 'monitor' in msg:
                self.monitor.start()
            else:
                self.monitor.stop()
            if 'detector' in msg:
                self.detector.start()
            else:
                self.detector.stop()
            # if 'mitigator' in msg:
            #     self.mitigator.start()
            # else:
            #     self.mitigator.stop()
            return service_pb2.Empty()

        def queryServiceState(self, request, context):
            return service_pb2.ServiceMessage(
                monitor=self.monitor.flag,
                detector=self.detector.flag,
                mitigator=False
            )

    def start(self, monitor, detector, mitigator=None):
        print("Starting GRPC Server...")
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        service_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.db, self.parsed_log_queue), self.grpc_server)
        service_pb2_grpc.add_ServiceListenerServicer_to_server(
            GrpcServer.ServiceGrpc(monitor, detector, mitigator), self.grpc_server)

        self.grpc_server.add_insecure_port('[::]:50051')
        _thread.start_new_thread(self.grpc_server.start, ())

    def stop(self):
        print("Stopping GRPC Server...")
        self.grpc_server.stop(0)
