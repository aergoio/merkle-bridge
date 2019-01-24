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
            self._addr1 = f.readline()[:52]
            self._addr2 = f.readline()[:52]
        self._t_anchor = config_data['t_anchor']
        self._t_final = config_data['t_final']
        print(" * anchoring periode : ", self._t_anchor, "s\n",
            "* chain finality periode : ", self._t_final, "s\n")

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(config_data['aergo1']['ip'])
        self._aergo2.connect(config_data['aergo2']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data['priv_key']["validator1"]
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        print("  > Sender Address: {}".format(sender_account.address))

    def GetAnchorSignature(self, request, context):
        """ Verifies the anchors are valid and signes them """
        if not self.is_valid_anchor(request):
            return bridge_operator_pb2.Approvals()

        print(request)
        # sign anchor and return approval
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

    def is_valid_anchor(self, request):
        """ An anchor is valid if it's height is finalized and
        if it's root for that height is correct.
        aergo1 and aergo2 must be trusted.
        """
        # get the last block height and check now > origin_height + t_final
        _, best_height1 = self._aergo1.get_blockchain_status()
        _, best_height2 = self._aergo2.get_blockchain_status()

        is_not_finalized1 = best_height1 < (int(request.anchor1.origin_height)
                                            + self._t_final)
        is_not_finalized2 = best_height2 < (int(request.anchor2.origin_height)
                                            + self._t_final)
        if is_not_finalized1 or is_not_finalized2:
            print("anchor not finalized")
            return False

        # get the last anchor and check origin_height > last_anchor + t_anchor
        # not necessary as the bridge contract should prevent root updates
        # before last_anchor + t_anchor: TODO

        # get contract state root at origin_height and check equals origin root
        block1 = self._aergo1.get_block(block_height=int(request.anchor1.origin_height))
        block2 = self._aergo2.get_block(block_height=int(request.anchor2.origin_height))
        contract1 = self._aergo1.get_account(address=self._addr1, proof=True,
                                    root=block1.blocks_root_hash)
        contract2 = self._aergo2.get_account(address=self._addr2, proof=True,
                                    root=block2.blocks_root_hash)
        root1 = contract1.state_proof.state.storageRoot.hex()
        root2 = contract2.state_proof.state.storageRoot.hex()

        is_invalid_root1 = root1 != request.anchor1.origin_root
        is_invalid_root2 = root2 != request.anchor2.origin_root
        if is_invalid_root1 or is_invalid_root2:
            print("root to sign doesnt match expected root")
            return False
        return True


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
