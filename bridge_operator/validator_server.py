import bridge_operator_pb2_grpc
import bridge_operator_pb2

from concurrent import futures
import grpc
import hashlib
import json
import time

import aergo.herapy as herapy

_ONE_DAY_IN_SECONDS = 60 * 60 * 24

class ValidatorServer(bridge_operator_pb2_grpc.BridgeOperatorServicer):
    """Validates anchors for the bridge proposer"""

    def __init__(self):
        with open("./config.json", "r") as f:
            config_data = json.load(f)
        with open("./bridge_operator/bridge_addresses.txt", "r") as f:
            addr1 = f.readline()[:52]
            addr2 = f.readline()[:52]
        t_anchor = config_data['t_anchor']
        t_final = config_data['t_final']
        print(" * anchoring periode : ", t_anchor, "s\n",
            "* chain finality periode : ", t_final, "s\n")

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(config_data['aergo1']['ip'])
        self._aergo2.connect(config_data['aergo2']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data['priv_key']["validator1"]
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        print("  > Sender Address: {}".format(sender_account.address))

    def GetSignature(self, request, context):
        """ Verifies the anchors are valid and signes them """
        print(request)
        msg1 = bytes(request.anchor1.origin_root
                     + request.anchor1.origin_height
                     + request.anchor1.nonce, 'utf-8')
        msg2 = bytes(request.anchor2.origin_root
                     + request.anchor2.origin_height
                     + request.anchor2.nonce, 'utf-8')
        h1 = hashlib.sha256(msg1).digest()
        h2 = hashlib.sha256(msg2).digest()
        sig1 = "0x" + self._aergo1.account.private_key.sign_msg(h1).hex()
        sig2 = "0x" + self._aergo1.account.private_key.sign_msg(h2).hex()
        approvals = bridge_operator_pb2.Approvals(address="address",
                                                  sig1=sig1,
                                                  sig2=sig2)
        return approvals


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    bridge_operator_pb2_grpc.add_BridgeOperatorServicer_to_server(
        ValidatorServer(), server)
    server.add_insecure_port('[::]:9841')
    server.start()
    print("server started")
    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == '__main__':
    serve()
