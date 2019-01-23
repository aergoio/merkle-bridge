import bridge_operator_pb2_grpc
import bridge_operator_pb2

from concurrent import futures
import grpc
import time

_ONE_DAY_IN_SECONDS = 60 * 60 * 24

class Server(bridge_operator_pb2_grpc.BridgeOperatorServicer):
    """Validates anchores for the bridge proposer"""

    def __init__(self):#, aergo1, aergo2):
        #self._aergo1 = aergo1
        #self._aergo2 = aergo2
        pass

    def GetSignature(self, request, context):
        """ Verifies the anchors are valid and signes them """
        print(request)
        approvals = bridge_operator_pb2.Approvals(address="address",
                                                  sig1="sig1",
                                                  sig2="sig2")
        return approvals


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    bridge_operator_pb2_grpc.add_BridgeOperatorServicer_to_server(
        Server(), server)
    server.add_insecure_port('[::]:9841')
    server.start()
    print("server started")
    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    # logging.basicConfig()
    serve()
