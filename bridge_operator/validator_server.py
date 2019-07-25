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
    Dict,
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
        self.config_file_path = config_file_path
        config_data = self.load_config_data()
        self.aergo1 = aergo1
        self.aergo2 = aergo2
        self.hera1 = herapy.Aergo()
        self.hera2 = herapy.Aergo()
        self.auto_update = auto_update

        print("------ Connect AERGO -----------")
        self.hera1.connect(config_data['networks'][aergo1]['ip'])
        self.hera2.connect(config_data['networks'][aergo2]['ip'])

        self.validator_index = validator_index
        self.addr1 = config_data['networks'][aergo1]['bridges'][aergo2]['addr']
        self.addr2 = config_data['networks'][aergo2]['bridges'][aergo1]['addr']
        self.id1 = config_data['networks'][aergo1]['bridges'][aergo2]['id']
        self.id2 = config_data['networks'][aergo2]['bridges'][aergo1]['id']

        # check validators are correct
        validators1 = query_validators(self.hera1, self.addr1)
        validators2 = query_validators(self.hera2, self.addr2)
        assert validators1 == validators2, \
            "Validators should be the same on both sides of bridge"
        print("Bridge validators : ", validators1)

        # get the current t_anchor and t_final for both sides of bridge
        t_anchor1, t_final1 = query_tempo(
            self.hera1, self.addr1, ["_sv_T_anchor", "_sv_T_final"]
        )
        t_anchor2, t_final2 = query_tempo(
            self.hera2, self.addr2, ["_sv_T_anchor", "_sv_T_final"]
        )
        print("{}             <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, t_final1, t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, t_final2, aergo2, t_anchor2))
        if auto_update:
            print("WARNING: This validator will vote for settings update in "
                  "config.json")
            if validators1 != validators2:
                print("WARNING: different validators on both sides "
                      "of the bridge")
            if len(config_data['validators']) != len(validators1):
                print("WARNING: This validator is voting for a new set of "
                      "aergo validators")
            if len(config_data['validators']) != len(validators2):
                print("WARNING: This validator is voting for a new set of "
                      "aergo validators")
            try:
                for i, validator in enumerate(config_data['validators']):
                    if validator['addr'] != validators1[i]:
                        print("WARNING: This validator is voting for a new "
                              "set of validators\n")
                    if validator['addr'] != validators2[i]:
                        print("WARNING: This validator is voting for a new "
                              "set of validators\n")
                    break
            except IndexError:
                pass

            t_anchor1_c = (config_data['networks'][self.aergo1]
                           ['bridges'][self.aergo2]['t_anchor'])
            t_final1_c = (config_data['networks'][self.aergo1]
                          ['bridges'][self.aergo2]['t_final'])
            t_anchor2_c = (config_data['networks'][self.aergo2]['bridges']
                           [self.aergo1]['t_anchor'])
            t_final2_c = (config_data['networks'][self.aergo2]['bridges']
                          [self.aergo1]['t_final'])
            if t_anchor1_c != t_anchor1:
                print("WARNING: This validator is voting to update anchoring "
                      "periode on mainnet")
            if t_final1_c != t_final1:
                print("WARNING: This validator is voting to update finality "
                      "of sidechain on mainnet")
            if t_anchor2_c != t_anchor2:
                print("WARNING: This validator is voting to update anchoring "
                      "periode on sidechain")
            if t_final2_c != t_final2:
                print("WARNING: This validator is voting to update finality "
                      "of mainnet on sidechain")

        print("------ Set Signer Account -----------")
        if privkey_name is None:
            privkey_name = 'validator'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = \
            config_data['wallet'][privkey_name]['priv_key']
        self.hera1.import_account(sender_priv_key, privkey_pwd)
        self.hera2.import_account(sender_priv_key, privkey_pwd)
        self.address = str(self.hera1.account.address)
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
            err_msg = self.is_valid_anchor(anchor, self.hera1,
                                           self.addr1,
                                           self.hera2, self.addr2)
            tab = "\t"*5
            destination = "sidechain"
            bridge_id = self.id2
        else:
            err_msg = self.is_valid_anchor(anchor, self.hera2,
                                           self.addr2,
                                           self.hera1, self.addr1)
            destination = "mainnet"
            bridge_id = self.id1
        if err_msg is not None:
            return Approval(error=err_msg)

        # sign anchor and return approval
        msg = bytes(
            anchor.root + ',' + anchor.height + anchor.destination_nonce
            + bridge_id + "R", 'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        sig = self.hera1.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        print("{0}{1} Validator {2} signed a new anchor for {3},\n"
              "{0}with nonce {4}"
              .format(tab, u'\u2693', self.validator_index, destination,
                      anchor.destination_nonce))
        return approval

    def is_valid_anchor(
        self,
        anchor,
        aergo_from: herapy.Aergo,
        bridge_from: str,
        aergo_to: herapy.Aergo,
        bridge_to: str,
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

        status = aergo_to.query_sc_state(bridge_to, ["_sv_Nonce",
                                                     "_sv_Height",
                                                     "_sv_T_anchor"])
        last_nonce_to, last_merged_height_from, t_anchor = \
            [int(proof.value) for proof in status.var_proofs]

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

    def load_config_data(self) -> Dict:
        with open(self.config_file_path, "r") as f:
            config_data = json.load(f)
        return config_data

    def GetTAnchorSignature(self, tempo_msg, context):
        """Get a vote(signature) from the validator to update the t_anchor
        setting in the Aergo bridge contract

        """
        if tempo_msg.is_from_mainnet:
            current_tempo = query_tempo(self.hera2, self.addr2,
                                        ["_sv_T_final"])
            return self.get_tempo(
                self.hera2, self.aergo1, self.aergo2, self.addr2, self.id2,
                tempo_msg, 't_anchor', "A", current_tempo, "\t"*5)
        else:
            current_tempo = query_tempo(self.hera1, self.addr1,
                                        ["_sv_T_final"])
            return self.get_tempo(
                self.hera1, self.aergo2, self.aergo1, self.addr1, self.id1,
                tempo_msg, 't_anchor', "A", current_tempo, "")

    def GetTFinalSignature(self, tempo_msg, context):
        """Get a vote(signature) from the validator to update the t_final
        setting in the Aergo bridge contract

        """
        if tempo_msg.is_from_mainnet:
            current_tempo = query_tempo(self.hera2, self.addr2,
                                        ["_sv_T_final"])
            return self.get_tempo(
                self.hera2, self.aergo1, self.aergo2, self.addr2, self.id2,
                tempo_msg, 't_final', "F", current_tempo, "\t"*5)
        else:
            current_tempo = query_tempo(self.hera1, self.addr1,
                                        ["_sv_T_final"])
            return self.get_tempo(
                self.hera1, self.aergo2, self.aergo1, self.addr1, self.id1,
                tempo_msg, 't_final', "F", current_tempo, "")

    def get_tempo(
        self,
        hera: herapy.Aergo,
        aergo_from: str,
        aergo_to: str,
        bridge_to: str,
        id_to: str,
        tempo_msg,
        tempo_str,
        tempo_id,
        current_tempo,
        tab
    ):
        if not self.auto_update:
            return Approval(error="Voting not enabled")
        # check destination nonce is correct
        nonce = int(hera.query_sc_state(
            bridge_to, ["_sv_Nonce"]
        ).var_proofs[0].value)
        if nonce != tempo_msg.destination_nonce:
            return Approval(error="Incorrect Nonce on {}".format(aergo_to))
        config_data = self.load_config_data()
        tempo = (config_data['networks'][aergo_to]['bridges']
                 [aergo_from][tempo_str])
        # check new tempo is different from current one to prevent
        # update spamming
        if current_tempo == tempo:
            return Approval(
                error="New {} is same as current one on {}"
                      .format(tempo_str, aergo_to))
        # check tempo matches the one in config
        if tempo != tempo_msg.tempo:
            return Approval(
                error="Refused to vote for this {}: {} on {}"
                      .format(tempo_str, tempo_msg.tempo, aergo_to)
            )
        # sign anchor and return approval
        msg = bytes(
            str(tempo) + str(nonce) + id_to + tempo_id,
            'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        sig = hera.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        print("{0}{1} Validator {2} signed a new {3} for {4},\n"
              "{0}with nonce {5}"
              .format(tab, u'\u231B', self.validator_index, tempo_str,
                      aergo_to, tempo_msg.destination_nonce))
        return approval

    def GetValidatorsSignature(self, val_msg, context):
        if val_msg.is_from_mainnet:
            return self.get_validators(
                self.hera2, self.addr2, self.id2,
                val_msg, "\t"*5)
        else:
            return self.get_validators(
                self.hera1, self.addr1, self.id1,
                val_msg, "")

    def get_validators(
        self,
        hera: herapy.Aergo,
        bridge_to: str,
        id_to: str,
        val_msg,
        tab
    ):
        if not self.auto_update:
            return Approval(error="Voting not enabled")
        # check destination nonce is correct
        nonce = int(
            hera.query_sc_state(
                bridge_to, ["_sv_Nonce"]).var_proofs[0].value
        )
        if nonce != val_msg.destination_nonce:
            return Approval(error="Incorrect Nonce")
        config_data = self.load_config_data()
        config_vals = [val['addr'] for val in config_data['validators']]
        # check new validators are different from current ones to prevent
        # update spamming
        current_validators = query_validators(hera, bridge_to)
        if current_validators == config_vals:
            return Approval(error="New validators are same as current ones")
        # check validators are same in config file
        if config_vals != val_msg.validators:
            return Approval(error="Refused to vote for this validator "
                                  "set: {}".format(val_msg.validators))
        # sign validators
        data = ""
        for val in config_vals:
            data += val
        data += str(nonce) + id_to + "V"
        data_bytes = bytes(data, 'utf-8')
        h = hashlib.sha256(data_bytes).digest()
        sig = hera.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        print("{0}{1} Validator {2} signed a new validator set for {3},\n"
              "{0}with nonce {4}"
              .format(tab, u'\U0001f58b', self.validator_index, "Aergo",
                      val_msg.destination_nonce))
        return approval


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
                               privkey_name, privkey_pwd, index, True)
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
