from concurrent import (
    futures,
)
from functools import (
    partial,
)
import grpc
import hashlib
import json
from multiprocessing.dummy import (
    Pool,
)
import time

import aergo.herapy as herapy

from bridge_operator.bridge_operator_pb2_grpc import (
    BridgeOperatorServicer,
    add_BridgeOperatorServicer_to_server,
)
from bridge_operator.bridge_operator_pb2 import (
    Approvals,
)
# import bridge_operator_pb2_grpc
# import bridge_operator_pb2


_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class ValidatorService(BridgeOperatorServicer):
    """Validates anchors for the bridge proposer"""

    def __init__(self, config_data, aergo1, aergo2, validator_index=0):
        self._validator_index = validator_index
        self._addr1 = config_data[aergo1]['bridges'][aergo2]['addr']
        self._addr2 = config_data[aergo2]['bridges'][aergo1]['addr']
        self._t_anchor1 = config_data[aergo1]['bridges'][aergo2]['t_anchor']
        self._t_final1 = config_data[aergo1]['bridges'][aergo2]['t_final']
        self._t_anchor2 = config_data[aergo2]['bridges'][aergo1]['t_anchor']
        self._t_final2 = config_data[aergo2]['bridges'][aergo1]['t_final']
        print("{}              <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, self._t_final2, self._t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, self._t_final1, aergo2, self._t_anchor2))

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(config_data[aergo1]['ip'])
        self._aergo2.connect(config_data[aergo2]['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data["validators"][validator_index]['priv_key']
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        self.address = sender_account.address.__str__()
        print("  > Sender Address: {}".format(self.address))

    def GetAnchorSignature(self, request, context):
        """ Verifies the anchors are valid and signes them """
        if not self.is_valid_anchor(request):
            return Approvals()

        print(request)
        # sign anchor and return approval
        msg1 = bytes(request.anchor1.root
                     + request.anchor1.height
                     + request.anchor1.destination_nonce, 'utf-8')
        msg2 = bytes(request.anchor2.root
                     + request.anchor2.height
                     + request.anchor2.destination_nonce, 'utf-8')
        h1 = hashlib.sha256(msg1).digest()
        h2 = hashlib.sha256(msg2).digest()
        sig1 = self._aergo1.account.private_key.sign_msg(h1)
        sig2 = self._aergo1.account.private_key.sign_msg(h2)
        approvals = Approvals(address=self.address, sig1=sig1, sig2=sig2)
        print("Validator ", self._validator_index, "signed a new anchor")
        return approvals

    def is_valid_anchor(self, request):
        """ An anchor is valid if :
            1- it's height is finalized
            2- it's root for that height is correct.
            3- it's nonce is correct
            4- it's height it higher than previous anchored height
            aergo1 and aergo2 must be trusted.
        """
        # 1- get the last block height and check now > origin_height + t_final
        _, best_height1 = self._aergo1.get_blockchain_status()
        _, best_height2 = self._aergo2.get_blockchain_status()

        # TODO use lib
        is_not_finalized1 = best_height1 < (int(request.anchor1.height)
                                            + self._t_final2)
        is_not_finalized2 = best_height2 < (int(request.anchor2.height)
                                            + self._t_final1)
        if is_not_finalized1 or is_not_finalized2:
            print("anchor not finalized", request)
            return False

        # get the last anchor and check origin_height > last_anchor + t_anchor
        # not necessary as the bridge contract should prevent root updates
        # before last_anchor + t_anchor

        # 2- get contract state root at origin_height and check equals anchor root
        block1 = self._aergo1.get_block(block_height=int(request.anchor1.height))
        block2 = self._aergo2.get_block(block_height=int(request.anchor2.height))
        contract1 = self._aergo1.get_account(address=self._addr1, proof=True,
                                             root=block1.blocks_root_hash)
        contract2 = self._aergo2.get_account(address=self._addr2, proof=True,
                                             root=block2.blocks_root_hash)
        root1 = contract1.state_proof.state.storageRoot.hex()
        root2 = contract2.state_proof.state.storageRoot.hex()

        is_invalid_root1 = root1 != request.anchor1.root
        is_invalid_root2 = root2 != request.anchor2.root
        if is_invalid_root1 or is_invalid_root2:
            print("root to sign doesnt match expected root\n", request)
            return False

        merge_info1 = self._aergo1.query_sc_state(self._addr1, ["_sv_Nonce",
                                                                "_sv_Height"])
        merge_info2 = self._aergo2.query_sc_state(self._addr2, ["_sv_Nonce",
                                                                "_sv_Height"])
        nonce1, merged_height2 = [int(proof.value) for proof in merge_info1.var_proofs]
        nonce2, merged_height1 = [int(proof.value) for proof in merge_info2.var_proofs]

        # 3- check merkle bridge nonces are correct
        is_invalid_nonce1 = nonce1 != int(request.anchor2.destination_nonce)
        is_invalid_nonce2 = nonce2 != int(request.anchor1.destination_nonce)
        if is_invalid_nonce1 or is_invalid_nonce2:
            print("root update nonce is invalid\n", request)
            return False

        # 4- check anchored height comes after the previous one
        is_invalid_height2 = merged_height2 >= int(request.anchor2.height)
        is_invalid_height1 = merged_height1 >= int(request.anchor1.height)
        if is_invalid_height1 or is_invalid_height2:
            print("root update height is invalid: must be higher than previous merge\n", request)
            return False
        return True


class ValidatorServer:

    def __init__(self, config_data, aergo1, aergo2, validator_index=0):
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_BridgeOperatorServicer_to_server(
            ValidatorService(config_data, aergo1, aergo2, validator_index),
            self.server)
        self.server.add_insecure_port(config_data['validators'][validator_index]['ip'])
        self.validator_index = validator_index

    def run(self):
        self.server.start()
        print("server", self.validator_index, " started")
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            print("\nShutting down validator")
            self.shutdown()

    def shutdown(self):
        self.server.stop(0)


def _serve(servers, index):
    servers[index].run()

def serve_all(config_data, aergo1, aergo2):
    validator_indexes = [i for i in range(len(config_data['validators']))]
    servers = [ValidatorServer(config_data, aergo1, aergo2, index) for index in validator_indexes]
    worker = partial(_serve, servers)
    pool = Pool(len(validator_indexes))
    pool.map(worker, validator_indexes)


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    # validator = ValidatorServer(config_data, 'mainnet', 'sidechain2')
    # validator.run()
    serve_all(config_data, 'mainnet', 'sidechain2')
