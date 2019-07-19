import argparse
from concurrent import (
    futures,
)
from functools import (
    partial,
)
from getpass import getpass
import grpc
import hashlib
import json
from multiprocessing.dummy import (
    Pool,
)
import time

from typing import (
    Optional,
)

import aergo.herapy as herapy

from bridge_operator.bridge_operator_pb2_grpc import (
    BridgeOperatorServicer,
    add_BridgeOperatorServicer_to_server,
)
from bridge_operator.bridge_operator_pb2 import (
    Approval,
)
from bridge_operator.op_utils import (
    query_tempo,
    query_validators,
)

_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class ValidatorService(BridgeOperatorServicer):
    """Validates anchors for the bridge proposer"""

    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        validator_index: int = 0,
        auto_update: bool = False,
    ) -> None:
        """
        aergo1 is considered to be the mainnet side of the bridge.
        Proposers should set anchor.is_from_mainnet accordingly
        """
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        self.aergo1 = herapy.Aergo()
        self.aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self.aergo1.connect(config_data['networks'][aergo1]['ip'])
        self.aergo2.connect(config_data['networks'][aergo2]['ip'])

        self._validator_index = validator_index
        self.addr1 = config_data['networks'][aergo1]['bridges'][aergo2]['addr']
        self.addr2 = config_data['networks'][aergo2]['bridges'][aergo1]['addr']
        self.id1 = config_data['networks'][aergo1]['bridges'][aergo2]['id']
        self.id2 = config_data['networks'][aergo2]['bridges'][aergo1]['id']

        # check validators are correct
        validators1 = query_validators(self.aergo1, self.addr1)
        validators2 = query_validators(self.aergo2, self.addr2)
        assert validators1 == validators2, \
            "Validators should be the same on both sides of bridge"
        print("Bridge validators : ", validators1)

        # get the current t_anchor and t_final for both sides of bridge
        self.t_anchor1, self.t_final1 = query_tempo(
            self.aergo1, self.addr1, ["_sv_T_anchor", "_sv_T_final"]
        )
        self.t_anchor2, self.t_final2 = query_tempo(
            self.aergo2, self.addr2, ["_sv_T_anchor", "_sv_T_final"]
        )
        print("{}             <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, self.t_final1, self.t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, self.t_final2, aergo2, self.t_anchor2))

        print("------ Set Signer Account -----------")
        if privkey_name is None:
            privkey_name = 'validator'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = \
            config_data['wallet'][privkey_name]['priv_key']
        self.aergo1.import_account(sender_priv_key, privkey_pwd)
        self.address = str(self.aergo1.account.address)
        print("  > Validator Address: {}".format(self.address))

    def GetAnchorSignature(self, anchor, context):
        """ Verifies the anchors are valid and signes them
            aergo1 and aergo2 must be trusted.
        """
        tab = ""
        destination = ""
        bridge_id = ""
        if anchor.is_from_mainnet:
            # aergo1 is considered to be mainnet side of bridge
            err_msg = self.is_valid_anchor(anchor, self.aergo1,
                                           self.addr1,
                                           self.aergo2, self.addr2,
                                           self.t_anchor2)
            tab = "\t"*5
            destination = "sidechain"
            bridge_id = self.id2
        else:
            err_msg = self.is_valid_anchor(anchor, self.aergo2,
                                           self.addr2,
                                           self.aergo1, self.addr1,
                                           self.t_anchor1)
            destination = "mainnet"
            bridge_id = self.id1
        if err_msg is not None:
            return Approval(error=err_msg)

        # sign anchor and return approval
        msg = bytes(
            anchor.root + ',' + anchor.height + ',' + anchor.destination_nonce
            + ',' + bridge_id + "R", 'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        sig = self.aergo1.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        print("{0}Validator {1} signed a new anchor for {2},\n"
              "{0}with nonce {3}"
              .format(tab, self._validator_index, destination,
                      anchor.destination_nonce))
        return approval

    def is_valid_anchor(
        self,
        anchor,
        aergo_from: herapy.Aergo,
        bridge_from: str,
        aergo_to: herapy.Aergo,
        bridge_to: str,
        t_anchor: int
    ) -> Optional[str]:
        """ An anchor is valid if :
            1- it's height is finalized
            2- it's root for that height is correct.
            3- it's nonce is correct
            4- it's height is higher than previous anchored height + t_anchor
        """
        # 1- get the last block height and check anchor height > LIB
        # lib = best_height - finalized_from
        lib = aergo_from.get_status().consensus_info.status['LibNo']
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
    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        validator_index: int = 0,
        auto_update: bool = False,
    ) -> None:
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        with open("./config.json", "r") as f:
            config_data = json.load(f)
        add_BridgeOperatorServicer_to_server(
            ValidatorService(config_file_path, aergo1, aergo2, privkey_name,
                             privkey_pwd, validator_index, auto_update),
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


def _serve_worker(servers, index):
    servers[index].run()


def _serve_all(config_file_path, aergo1, aergo2,
               privkey_name=None, privkey_pwd=None):
    """ For testing, run all validators in different threads """
    with open(config_file_path, "r") as f:
        config_data = json.load(f)
    validator_indexes = [i for i in range(len(config_data['validators']))]
    servers = [ValidatorServer(config_file_path, aergo1, aergo2,
                               privkey_name, privkey_pwd, index)
               for index in validator_indexes]
    worker = partial(_serve_worker, servers)
    pool = Pool(len(validator_indexes))
    pool.map(worker, validator_indexes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Start a validator between 2 Aergo networks.')
    # Add arguments
    parser.add_argument(
        '-c', '--config_file_path', type=str, help='Path to config.json',
        required=True)
    parser.add_argument(
        '--net1', type=str, help='Name of Aergo network in config file',
        required=True)
    parser.add_argument(
        '--net2', type=str, help='Name of Aergo network in config file',
        required=True)
    parser.add_argument(
        '-i', '--validator_index', type=int, required=True,
        help='Index of the validator in the ordered list of validators')
    parser.add_argument(
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)
    parser.add_argument(
        '--auto_update', dest='auto_update', action='store_true',
        help='Update bridge contract when settings change in config file')
    parser.add_argument(
        '--local_test', dest='local_test', action='store_true',
        help='Start all validators locally for convenient testing')
    parser.set_defaults(auto_update=False)
    parser.set_defaults(local_test=False)

    args = parser.parse_args()

    if args.local_test:
        _serve_all(args.config_file_path, args.net1, args.net2,
                   privkey_name=args.privkey_name, privkey_pwd='1234')
    else:
        validator = ValidatorServer(
            args.config_file_path, args.net1, args.net2,
            privkey_name=args.privkey_name,
            validator_index=args.validator_index,
            auto_update=args.auto_update
        )
        validator.run()
