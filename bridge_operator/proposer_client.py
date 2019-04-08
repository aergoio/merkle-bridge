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
_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class ValidatorMajorityError(Exception):
    pass


class ProposerClient:
    """The bridge proposer periodically (every t_anchor) broadcasts
    the finalized trie state root (after t_final) of the bridge contract
    on both sides of the bridge after validation by the Validator servers.
    It first checks the last merged height and waits until
    now + t_anchor + t_final is reached, then merges the current finalised
    block (now - t_final). Start again after waiting t_anchor.
    """

    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        self._config_data = config_data
        self._addr1 = config_data[aergo1]['bridges'][aergo2]['addr']
        self._addr2 = config_data[aergo2]['bridges'][aergo1]['addr']
        self._id1 = config_data[aergo1]['bridges'][aergo2]['id']
        self._id2 = config_data[aergo2]['bridges'][aergo1]['id']

        print("------ Connect AERGO -----------")
        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        self._aergo1.connect(self._config_data[aergo1]['ip'])
        self._aergo2.connect(self._config_data[aergo2]['ip'])

        print("------ Connect to Validators -----------")
        validators1 = query_validators(self._aergo1, self._addr1)
        validators2 = query_validators(self._aergo2, self._addr2)
        assert validators1 == validators2, \
            "Validators should be the same on both sides of bridge"
        # create all channels with validators
        self._channels: List[grpc._channel.Channel] = []
        self._stubs: List[BridgeOperatorStub] = []
        for i, validator in enumerate(self._config_data['validators']):
            assert validators1[i] == validator['addr'], \
                "Validators in config file do not match bridge validators"\
                "Expected validators: {}".format(validators1)
            ip = validator['ip']
            channel = grpc.insecure_channel(ip)
            stub = BridgeOperatorStub(channel)
            self._channels.append(channel)
            self._stubs.append(stub)

        self._pool = Pool(len(self._stubs))

        # get the current t_anchor and t_final for both sides of bridge
        self._t_anchor1, self._t_final1 = query_tempo(
            self._aergo1, self._addr1, ["_sv_T_anchor", "_sv_T_final"]
        )
        self._t_anchor2, self._t_final2 = query_tempo(
            self._aergo2, self._addr2, ["_sv_T_anchor", "_sv_T_final"]
        )
        print("{}              <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, self._t_final1, self._t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, self._t_final2, aergo2, self._t_anchor2))

        print("------ Set Sender Account -----------")
        if privkey_name is None:
            privkey_name = 'proposer'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = self._config_data['wallet'][privkey_name]['priv_key']
        self._aergo1.import_account(sender_priv_key, privkey_pwd)
        self._aergo2.import_account(sender_priv_key, privkey_pwd)
        print("  > Proposer Address: {}".format(self._aergo1.account.address))

        self.kill_proposer_threads = False

    def get_validators_signatures(
        self,
        anchor_msg: Tuple[bool, str, int, int],
        to_bridge_id: str,
        tab: str
    ) -> Tuple[List[str], List[int]]:
        """ Query all validators and gather 2/3 of their signatures. """
        is_from_mainnet, root, merge_height, nonce = anchor_msg

        # messages to get signed
        msg_str = root + str(merge_height) + str(nonce) + to_bridge_id + "R"
        msg = bytes(msg_str, 'utf-8')
        h = hashlib.sha256(msg).digest()

        anchor = Anchor(is_from_mainnet=is_from_mainnet,
                        root=root,
                        height=str(merge_height),
                        destination_nonce=str(nonce))

        # get validator signatures and verify sig in worker
        validator_indexes = [i for i in range(len(self._stubs))]
        worker = partial(self.get_signature_worker, tab, anchor, h)
        approvals = self._pool.map(worker, validator_indexes)

        sigs, validator_indexes = self.extract_signatures(approvals)

        return sigs, validator_indexes

    def get_signature_worker(
        self,
        tab: str,
        anchor,
        h: bytes,
        index: int
    ) -> Optional[Any]:
        """ Get a validator's (index) signature and verify it"""
        try:
            approval = self._stubs[index].GetAnchorSignature(anchor)
        except grpc.RpcError:
            return None
        if approval.error:
            print("{}{}".format(tab, approval.error))
            return None
        if approval.address != self._config_data['validators'][index]['addr']:
            # check nothing is wrong with validator address
            print("{}Unexpected validato {} address : {}"
                  .format(tab, index, approval.address))
            return None
        # validate signature
        if not verify_sig(h, approval.sig, approval.address):
            print("{}Invalid signature from validator {}"
                  .format(tab, index))
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

    @staticmethod
    def wait_next_anchor(
        merged_height: int,
        aergo: herapy.Aergo,
        t_final: int,
        t_anchor: int
    ) -> int:
        """ Wait until t_anchor has passed after merged height.
        Return the next finalized block after t_anchor to be the next anchor
        """
        _, best_height = aergo.get_blockchain_status()
        # TODO use real lib from rpc
        lib = best_height - t_final
        wait = (merged_height + t_anchor) - lib
        while wait > 0:
            print("waiting new anchor time :", wait, "s ...")
            time.sleep(wait)
            # Get origin and destination best height
            _, best_height = aergo.get_blockchain_status()
            # Wait best height - t_final >= merge block height + t_anchor
            lib = best_height - t_final
            wait = (merged_height + t_anchor) - lib
        return lib

    def set_root(
        self,
        aergo_to: herapy.Aergo,
        bridge_to: str,
        args: Tuple[str, int, List[int], List[str]],
        t_anchor_to: int,
        tab: str
    ) -> None:
        """Anchor a new root on chain"""
        tx, result = aergo_to.call_sc(bridge_to, "set_root",
                                      args=args)
        if result.status != herapy.CommitStatus.TX_OK:
            print("{}Anchor on aergo Tx commit failed : {}"
                  .format(tab, result))
            return

        time.sleep(COMMIT_TIME)
        result = aergo_to.get_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            print("{}Anchor failed: already anchored, or invalid "
                  "signature: {}".format(tab, result))
        else:
            print("{0}Anchor success,\n{0}wait until next anchor "
                  "time: {1}s...".format(tab, t_anchor_to))

    def bridge_worker(
        self,
        t_anchor_to: int,
        t_final_from: int,
        aergo_from: herapy.Aergo,
        aergo_to: herapy.Aergo,
        bridge_from: str,
        bridge_to: str,
        is_from_mainnet: bool,
        to_bridge_id: str,
        tab: str = ""
    ) -> None:
        """ Thread that anchors in one direction given t_final and t_anchor.
        Gathers signatures from validators, verifies them, and if 2/3 majority
        is acquired, set the new anchored root in bridge_to.
        """
        while True:  # anchor a new root
            # Get last merge information
            merge_info_from = aergo_to.query_sc_state(bridge_to,
                                                      ["_sv_Height",
                                                       "_sv_Root",
                                                       "_sv_Nonce"
                                                       ])
            merged_height_from, merged_root_from, nonce_to = \
                [proof.value for proof in merge_info_from.var_proofs]
            merged_height_from = int(merged_height_from)
            nonce_to = int(nonce_to)

            print("{0} __\n"
                  "{0}| last merged height: {1}\n"
                  "{0}| last merged contract trie root: {2}...\n"
                  "{0}| current update nonce: {3}\n"
                  .format(tab, merged_height_from,
                          merged_root_from.decode('utf-8')[1:20], nonce_to))

            while True:  # try to gather 2/3 validators
                # Wait for the next anchor time
                next_anchor_height = self.wait_next_anchor(merged_height_from,
                                                           aergo_from,
                                                           t_final_from,
                                                           t_anchor_to)
                # Get root of next anchor to broadcast
                block = aergo_from.get_block(block_height=next_anchor_height)
                contract = aergo_from.get_account(address=bridge_from,
                                                  proof=True,
                                                  root=block.blocks_root_hash)
                root = contract.state_proof.state.storageRoot.hex()
                if len(root) == 0:
                    print("{}waiting deployment finalization...".format(tab))
                    time.sleep(t_final_from/4)
                    continue

                print("{}anchoring new root :'0x{}...'"
                      .format(tab, root[:17]))
                print("{}Gathering signatures from validators ..."
                      .format(tab))

                try:
                    anchor_msg = is_from_mainnet, root, next_anchor_height, \
                        nonce_to
                    sigs, validator_indexes = \
                        self.get_validators_signatures(anchor_msg,
                                                       to_bridge_id, tab)
                except ValidatorMajorityError:
                    print("{0}Failed to gather 2/3 validators signatures,\n"
                          "{0}waiting for next anchor..."
                          .format(tab))
                    if self.kill_proposer_threads:
                        print("{}stopping thread".format(tab))
                        return
                    time.sleep(t_anchor_to)
                    continue
                break

            # don't broadcast if somebody else already did
            last_merge = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
            merged_height = int(last_merge.var_proofs[0].value)
            if merged_height + t_anchor_to >= next_anchor_height:
                print("{}Another proposer already anchored".format(tab))
                time.sleep(t_anchor_to)
                continue

            # Broadcast finalised merge block
            args = (root, next_anchor_height, validator_indexes, sigs)
            self.set_root(aergo_to, bridge_to, args, t_anchor_to, tab)

            if self.kill_proposer_threads:
                print("{}stopping thread".format(tab))
                return

            # Wait t_anchor
            # counting commit time in t_anchor often leads to 'Next anchor not
            # reached exception.
            time.sleep(t_anchor_to)

    def run(self):
        self.kill_proposer_threads = False
        print("------ START BRIDGE OPERATOR -----------\n")
        print("{}MAINNET{}SIDECHAIN".format("\t", "\t"*4))
        to_2_args = (self._t_anchor2, self._t_final2,
                     self._aergo1, self._aergo2,
                     self._addr1, self._addr2, True, self._id2, "\t"*5)
        to_1_args = (self._t_anchor1, self._t_final1,
                     self._aergo2, self._aergo1,
                     self._addr2, self._addr1, False, self._id1)
        t_mainnet = threading.Thread(target=self.bridge_worker,
                                     args=to_2_args)
        t_sidechain = threading.Thread(target=self.bridge_worker,
                                       args=to_1_args)
        t_mainnet.start()
        t_sidechain.start()
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            print("\nInitiating proposer shutdown, finalizing last anchors")
            self.kill_proposer_threads = True
            t_mainnet.join()
            t_sidechain.join()
            self.shutdown()

    def shutdown(self):
        print("\nDisconnecting AERGO")
        self._aergo1.disconnect()
        self._aergo2.disconnect()
        print("Closing channels")
        for channel in self._channels:
            channel.close()


if __name__ == '__main__':
    proposer = ProposerClient("./config.json", 'mainnet', 'sidechain2')
    proposer.run()
