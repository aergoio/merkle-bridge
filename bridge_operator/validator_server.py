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
    Approval,
)

_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class ValidatorService(BridgeOperatorServicer):
    """Validates anchors for the bridge proposer"""

    def __init__(self, config_data, aergo1, aergo2, validator_index=0):
        """
        aergo1 is considered to be the mainnet side of the bridge.
        Proposers should set anchor.is_from_mainnet accordingly
        """
        self._validator_index = validator_index
        self._addr1 = config_data[aergo1]['bridges'][aergo2]['addr']
        self._addr2 = config_data[aergo2]['bridges'][aergo1]['addr']
        self._t_anchor1 = config_data[aergo1]['bridges'][aergo2]['t_anchor']
        self._t_final1 = config_data[aergo1]['bridges'][aergo2]['t_final']
        self._t_anchor2 = config_data[aergo2]['bridges'][aergo1]['t_anchor']
        self._t_final2 = config_data[aergo2]['bridges'][aergo1]['t_final']
        print("{}             <- {} (t_final={}) : t_anchor={}"
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

    def GetAnchorSignature(self, anchor, context):
        """ Verifies the anchors are valid and signes them
            aergo1 and aergo2 must be trusted.
        """
        tab = ""
        destination = ""
        if anchor.is_from_mainnet:
            # aergo1 is considered to be mainnet side of bridge
            err_msg = self.is_valid_anchor(anchor, self._aergo1,
                                           self._addr1, self._t_final2,
                                           self._aergo2, self._addr2,
                                           self._t_anchor2)
            tab = "\t"*5
            destination = "sidechain"
        else:
            err_msg = self.is_valid_anchor(anchor, self._aergo2,
                                           self._addr2, self._t_final1,
                                           self._aergo1, self._addr1,
                                           self._t_anchor1)
            destination = "mainnet"
        if err_msg is not None:
            return Approval(error=err_msg)

        # sign anchor and return approval
        msg = bytes(anchor.root + anchor.height
                    + anchor.destination_nonce, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = self._aergo1.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        print("{0}Validator {1} signed a new anchor for {2},\n"
              "{0}with nonce {3}"
              .format(tab, self._validator_index, destination,
                      anchor.destination_nonce))
        return approval

    def is_valid_anchor(self, anchor, aergo_from, bridge_from, finalized_from,
                        aergo_to, bridge_to, t_anchor):
        """ An anchor is valid if :
            1- it's height is finalized
            2- it's root for that height is correct.
            3- it's nonce is correct
            4- it's height is higher than previous anchored height + t_anchor
        """
        # 1- get the last block height and check now > origin_height + t_final
        # TODO use real lib from rpc
        _, best_height = aergo_from.get_blockchain_status()
        lib = best_height - finalized_from
        if int(anchor.height) > lib:
            print("anchor not finalized\n", anchor)
            return "anchor not finalized"

        # 2- get contract state root at origin_height
        # and check equals anchor root
        block = aergo_from.get_block(block_height=int(anchor.height))
        contract = aergo_from.get_account(address=bridge_from, proof=True,
                                          root=block.blocks_root_hash)
        root = contract.state_proof.state.storageRoot.hex()
        if root != anchor.root:
            print("root to sign doesnt match expected root\n", anchor)
            return "root to sign doesnt match expected root"

        merge_info = aergo_to.query_sc_state(bridge_to, ["_sv_Nonce",
                                                         "_sv_Height"])
        last_nonce_to, last_merged_height_from = \
            [int(proof.value) for proof in merge_info.var_proofs]

        # 3- check merkle bridge nonces are correct
        if last_nonce_to != int(anchor.destination_nonce):
            print("anchor nonce is invalid\n", anchor)
            return "anchor nonce is invalid"

        # 4- check anchored height comes after the previous one and t_anchor is
        # passed
        if last_merged_height_from + t_anchor > int(anchor.height):
            print("root update height is invalid: "
                  "must be higher than previous merge + t_anchor\n", anchor)
            return "root update height is invalid"
        return None


class ValidatorServer:
    def __init__(self, config_data, aergo1, aergo2, validator_index=0):
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_BridgeOperatorServicer_to_server(
            ValidatorService(config_data, aergo1, aergo2, validator_index),
            self.server)
        self.server.add_insecure_port(config_data['validators']
                                      [validator_index]['ip'])
        self.validator_index = validator_index

    def run(self):
        self.server.start()
        print("server", self.validator_index, " started")
        print("{}MAINNET{}SIDECHAIN".format("\t", "\t"*4))
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


def _serve_all(config_data, aergo1, aergo2):
    """ For testing, run all validators in different threads """
    validator_indexes = [i for i in range(len(config_data['validators']))]
    servers = [ValidatorServer(config_data, aergo1, aergo2, index)
               for index in validator_indexes]
    worker = partial(_serve, servers)
    pool = Pool(len(validator_indexes))
    pool.map(worker, validator_indexes)


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    # validator = ValidatorServer(config_data, 'mainnet', 'sidechain2')
    # validator.run()
    _serve_all(config_data, 'mainnet', 'sidechain2')
