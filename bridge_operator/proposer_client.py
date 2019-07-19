import argparse
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
import threading
import time

from typing import (
    Tuple,
    Optional,
    List,
    Any,
)

import aergo.herapy as herapy
from aergo.herapy.utils.signature import (
    verify_sig,
)

from bridge_operator.bridge_operator_pb2_grpc import (
    BridgeOperatorStub,
)
from bridge_operator.bridge_operator_pb2 import (
    Anchor,
)
from bridge_operator.op_utils import (
    query_tempo,
    query_validators,
)

COMMIT_TIME = 3


class ValidatorMajorityError(Exception):
    pass


class ProposerClient(threading.Thread):
    """The proposer client periodically (every t_anchor) broadcasts
    the finalized trie state root (after lib) of the bridge contract
    on the other side of the bridge after validation by the Validator servers.
    It first checks the last merged height and waits until
    now > lib + t_anchor is reached, then merges the current finalised
    block (lib). Start again after waiting t_anchor.
    """

    def __init__(
        self,
        config_file_path: str,
        aergo_from: str,
        aergo_to: str,
        is_from_mainnet: bool,
        privkey_name: str = None,
        privkey_pwd: str = None,
        tab: str = "",
        auto_update: bool = False
    ) -> None:
        threading.Thread.__init__(self)
        self.tab = tab
        self.is_from_mainnet = is_from_mainnet
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        self._config_data = config_data

        print("------ Connect AERGO -----------")
        self.hera_from = herapy.Aergo()
        self.hera_to = herapy.Aergo()

        self.hera_from.connect(self._config_data['networks'][aergo_from]['ip'])
        self.hera_to.connect(self._config_data['networks'][aergo_to]['ip'])

        self.bridge_from = config_data['networks'][aergo_from]['bridges'][aergo_to]['addr']
        self.bridge_to = config_data['networks'][aergo_to]['bridges'][aergo_from]['addr']
        self.bridge_to_id = config_data['networks'][aergo_to]['bridges'][aergo_from]['id']

        print("------ Connect to Validators -----------")
        validators = query_validators(self.hera_to, self.bridge_to)
        print("Validators: ", validators)
        # create all channels with validators
        self.channels: List[grpc._channel.Channel] = []
        self.stubs: List[BridgeOperatorStub] = []
        for i, validator in enumerate(self._config_data['validators']):
            assert validators[i] == validator['addr'], \
                "Validators in config file do not match bridge validators"\
                "Expected validators: {}".format(validators)
            ip = validator['ip']
            channel = grpc.insecure_channel(ip)
            stub = BridgeOperatorStub(channel)
            self.channels.append(channel)
            self.stubs.append(stub)

        self.pool = Pool(len(self.stubs))

        # get the current t_anchor and t_final for both sides of bridge
        self.t_anchor, self.t_final = query_tempo(
            self.hera_to, self.bridge_to, ["_sv_T_anchor", "_sv_T_final"]
        )
        print("{} (t_final={}) -> {}  : t_anchor={}"
              .format(aergo_from, self.t_final, aergo_to, self.t_anchor))

        print("------ Set Sender Account -----------")
        if privkey_name is None:
            privkey_name = 'proposer'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = self._config_data['wallet'][privkey_name]['priv_key']
        self.hera_to.import_account(sender_priv_key, privkey_pwd)
        print(" > Proposer Address: {}".format(self.hera_to.account.address))

    def get_validators_signatures(
        self,
        root: str,
        merge_height: int,
        nonce: int,
    ) -> Tuple[List[str], List[int]]:
        """ Query all validators and gather 2/3 of their signatures. """

        # messages to get signed
        msg_str = root + ',' + str(merge_height) + ',' + str(nonce) + ',' \
            + self.bridge_to_id + "R"
        msg = bytes(msg_str, 'utf-8')
        h = hashlib.sha256(msg).digest()

        anchor = Anchor(
            is_from_mainnet=self.is_from_mainnet, root=root,
            height=str(merge_height), destination_nonce=str(nonce))

        # get validator signatures and verify sig in worker
        validator_indexes = [i for i in range(len(self.stubs))]
        worker = partial(self.get_signature_worker, anchor, h)
        approvals = self.pool.map(worker, validator_indexes)

        sigs, validator_indexes = self.extract_signatures(approvals)

        return sigs, validator_indexes

    def get_signature_worker(
        self,
        anchor,
        h: bytes,
        index: int
    ) -> Optional[Any]:
        """ Get a validator's (index) signature and verify it"""
        try:
            approval = self.stubs[index].GetAnchorSignature(anchor)
        except grpc.RpcError as e:
            print(e)
            return None
        if approval.error:
            print("{}{}".format(self.tab, approval.error))
            return None
        if approval.address != self._config_data['validators'][index]['addr']:
            # check nothing is wrong with validator address
            print("{}Unexpected validato {} address : {}"
                  .format(self.tab, index, approval.address))
            return None
        # validate signature
        if not verify_sig(h, approval.sig, approval.address):
            print("{}Invalid signature from validator {}"
                  .format(self.tab, index))
            return None
        return approval

    def extract_signatures(
        self,
        approvals: List[Any]
    ) -> Tuple[List[str], List[int]]:
        """ Convert signatures to hex string and keep 2/3 of them."""
        sigs, validator_indexes = [], []
        for i, approval in enumerate(approvals):
            if approval is not None:
                # convert to hex string for lua
                sigs.append('0x' + approval.sig.hex())
                validator_indexes.append(i+1)
        total_validators = len(self._config_data['validators'])
        if 3 * len(sigs) < 2 * total_validators:
            raise ValidatorMajorityError()
        # slice 2/3 of total validators
        two_thirds = ((total_validators * 2) // 3
                      + ((total_validators * 2) % 3 > 0))
        return sigs[:two_thirds], validator_indexes[:two_thirds]

    def wait_next_anchor(
        self,
        merged_height: int,
    ) -> int:
        """ Wait until t_anchor has passed after merged height.
        Return the next finalized block after t_anchor to be the next anchor
        """
        lib = self.hera_from.get_status().consensus_info.status['LibNo']
        wait = (merged_height + self.t_anchor) - lib + 1
        while wait > 0:
            print("waiting new anchor time :", wait, "s ...")
            time.sleep(wait)
            # Wait lib > last merged block height + t_anchor
            lib = self.hera_from.get_status().consensus_info.status['LibNo']
            wait = (merged_height + self.t_anchor) - lib + 1
        return lib

    def set_root(
        self,
        root: str,
        next_anchor_height: int,
        validator_indexes: List[int],
        sigs: List[str],
    ) -> None:
        """Anchor a new root on chain"""
        tx, result = self.hera_to.call_sc(
            self.bridge_to, "set_root",
            args=[root, next_anchor_height, validator_indexes, sigs]
        )
        if result.status != herapy.CommitStatus.TX_OK:
            print("{}Anchor on aergo Tx commit failed : {}"
                  .format(self.tab, result))
            return

        time.sleep(COMMIT_TIME)
        result = self.hera_to.get_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            print("{}Anchor failed: already anchored, or invalid "
                  "signature: {}".format(self.tab, result))
        else:
            print("{0}Anchor success,\n{0}wait until next anchor "
                  "time: {1}s...".format(self.tab, self.t_anchor))

    def run(
        self,
    ) -> None:
        """ Gathers signatures from validators, verifies them, and if 2/3 majority
        is acquired, set the new anchored root in bridge_to.
        """
        while True:  # anchor a new root
            # Get last merge information
            merge_info_from = self.hera_to.query_sc_state(
                self.bridge_to, ["_sv_Height", "_sv_Root", "_sv_Nonce"]
            )
            merged_height_from, merged_root_from, nonce_to = \
                [proof.value for proof in merge_info_from.var_proofs]
            merged_height_from = int(merged_height_from)
            nonce_to = int(nonce_to)

            print("{0} __\n"
                  "{0}| last merged height: {1}\n"
                  "{0}| last merged contract trie root: {2}...\n"
                  "{0}| current update nonce: {3}\n"
                  .format(self.tab, merged_height_from,
                          merged_root_from.decode('utf-8')[1:20], nonce_to))

            while True:  # try to gather 2/3 validators
                # Wait for the next anchor time
                next_anchor_height = self.wait_next_anchor(merged_height_from)
                # Get root of next anchor to broadcast
                block = self.hera_from.get_block(
                    block_height=next_anchor_height
                )
                contract = self.hera_from.get_account(
                    address=self.bridge_from, proof=True,
                    root=block.blocks_root_hash
                )
                root = contract.state_proof.state.storageRoot.hex()
                if len(root) == 0:
                    print("{}waiting deployment finalization..."
                          .format(self.tab))
                    time.sleep(5)
                    continue

                print("{}anchoring new root :'0x{}...'"
                      .format(self.tab, root[:17]))
                print("{}Gathering signatures from validators ..."
                      .format(self.tab))

                try:
                    sigs, validator_indexes = self.get_validators_signatures(
                        root, next_anchor_height, nonce_to
                    )
                except ValidatorMajorityError:
                    print("{0}Failed to gather 2/3 validators signatures,\n"
                          "{0}waiting for next anchor..."
                          .format(self.tab))
                    time.sleep(self.t_anchor)
                    continue
                break

            # don't broadcast if somebody else already did
            last_merge = self.hera_to.query_sc_state(self.bridge_to,
                                                     ["_sv_Height"])
            merged_height = int(last_merge.var_proofs[0].value)
            if merged_height + self.t_anchor >= next_anchor_height:
                print("{}Not yet anchor time"
                      "or another proposer already anchored".format(self.tab))
                time.sleep(merged_height + self.t_anchor - next_anchor_height)
                continue

            # Broadcast finalised merge block
            self.set_root(root, next_anchor_height, validator_indexes, sigs)

            # Wait t_anchor
            # counting commit time in t_anchor often leads to 'Next anchor not
            # reached exception.
            time.sleep(self.t_anchor)

    def shutdown(self):
        print("\nDisconnecting AERGO")
        self.hera_from.disconnect()
        self.hera_to.disconnect()
        print("Closing channels")
        for channel in self.channels:
            channel.close()


class BridgeProposerClient:
    """ The BridgeProposerClient starts proposers on both sides of the bridge
    """

    def __init__(
        self,
        config_file_path: str,
        aergo_mainnet: str,
        aergo_sidechain: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        auto_update: bool = False
    ) -> None:
        self.t_proposer1 = ProposerClient(
            config_file_path, aergo_mainnet, aergo_sidechain, True,
            privkey_name, privkey_pwd, "", auto_update
        )
        self.t_proposer2 = ProposerClient(
            config_file_path, aergo_sidechain, aergo_mainnet, False,
            privkey_name, privkey_pwd, "\t"*5, auto_update
        )

    def run(self):
        self.t_proposer1.start()
        self.t_proposer2.start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Start a proposer between 2 Aergo networks.')
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
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)
    parser.add_argument(
        '--auto_update', dest='auto_update', action='store_true',
        help='Update bridge contract when settings change in config file')
    parser.set_defaults(auto_update=False)
    args = parser.parse_args()
    proposer = BridgeProposerClient(
        args.config_file_path, args.net1, args.net2,
        privkey_name=args.privkey_name, auto_update=args.auto_update
    )
    proposer.run()
