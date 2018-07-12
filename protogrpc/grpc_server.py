import grpc
from protogrpc import mservice_pb2, hservice_pb2
from protogrpc import mservice_pb2_grpc, hservice_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from sqlalchemy import exc
from webapp.data.models import Monitor, db
from webapp import app
import traceback


class GrpcServer():

    def __init__(self, monitor, detector, mitigator):
        self.server_process = None

        self.monitor = monitor
        self.detector = detector
        self.mitigator = mitigator

    class MonitorGrpc(mservice_pb2_grpc.MessageListenerServicer):

        def __init__(self, detector):
            self.detector = detector

        def queryMformat(self, request, context):

            with app.app_context():
                monitor_event = Monitor(protobuf_to_dict(request))

                try:
                    db.session.add(monitor_event)
                    db.session.commit()
                    if monitor_event.type == 'A' and self.detector.flag:
                        self.detector.monitor_queue.put(monitor_event)
                except exc.SQLAlchemyError as e:
                    db.session.rollback()
                    duplicate_entry_str = "(sqlite3.IntegrityError) UNIQUE constraint failed"
                    if duplicate_entry_str not in str(e):
                        traceback.print_exc()

            return mservice_pb2.Empty()

    class HijackGrpc(hservice_pb2_grpc.MessageListenerServicer):

        def __init__(self, mitigator):
            self.mitigator = mitigator

        def queryHformat(self, request, context):
            hijack_id = int(protobuf_to_dict(request)['id'])

            if self.mitigator.flag:
                self.mitigator.hijack_queue.put(hijack_id)

            return hservice_pb2.Empty()

    def start(self):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        mservice_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.detector),
            self.grpc_server
        )

        hservice_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.HijackGrpc(self.mitigator),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')
        _thread.start_new_thread(self.grpc_server.start, ())
        print("GRPC Server Started..")

    def stop(self):
        self.grpc_server.stop(0)
        print("GRPC Server Stopped..")
