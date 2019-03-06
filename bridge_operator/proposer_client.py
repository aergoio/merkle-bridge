from functools import (
    partial,
)
import grpc
import hashlib
import json
from multiprocessing.dummy import (
    Pool,
)
import threading
import time

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

    def __init__(self, config_data, aergo1, aergo2):
        self._config_data = config_data
        self._addr1 = config_data[aergo1]['bridges'][aergo2]['addr']
        self._addr2 = config_data[aergo2]['bridges'][aergo1]['addr']

        print("------ Connect to Validators -----------")
        # create all channels with validators
        self._channels = []
        self._stubs = []
        for validator in self._config_data['validators']:
            ip = validator['ip']
            channel = grpc.insecure_channel(ip)
            stub = BridgeOperatorStub(channel)
            self._channels.append(channel)
            self._stubs.append(stub)

        self._pool = Pool(len(self._stubs))

        self._t_anchor1 = config_data[aergo1]['bridges'][aergo2]['t_anchor']
        self._t_final1 = config_data[aergo1]['bridges'][aergo2]['t_final']
        self._t_anchor2 = config_data[aergo2]['bridges'][aergo1]['t_anchor']
        self._t_final2 = config_data[aergo2]['bridges'][aergo1]['t_final']
        print("{}              <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, self._t_final1, self._t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, self._t_final2, aergo2, self._t_anchor2))

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(self._config_data[aergo1]['ip'])
        self._aergo2.connect(self._config_data[aergo2]['ip'])

        sender_priv_key1 = self._config_data["proposer"]['priv_key']
        sender_priv_key2 = self._config_data["proposer"]['priv_key']
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        self._aergo2.new_account(private_key=sender_priv_key2)
        self._aergo1.get_account()
        self._aergo2.get_account()
        print("  > Proposer Address: {}".format(sender_account.address))

        self.kill_proposer_threads = False

    def get_validators_signatures(self, anchor_msg, tab):
        is_from_mainnet, root, merge_height, nonce = anchor_msg

        # messages to get signed
        msg = bytes(root + str(merge_height) + str(nonce), 'utf-8')
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

    def get_signature_worker(self, tab, anchor, h, index):
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

    def extract_signatures(self, approvals):
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
    def wait_next_anchor(merged_height, aergo, t_final, t_anchor):
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

    def run(self):
        self.kill_proposer_threads = False
        print("------ START BRIDGE OPERATOR -----------\n")
        print("{}MAINNET{}SIDECHAIN".format("\t", "\t"*4))
        from_mainnet_args = (self._t_anchor2, self._t_final2,
                             self._aergo1, self._aergo2,
                             self._addr1, self._addr2, True, "\t"*5)
        to_mainnet_args = (self._t_anchor1, self._t_final1,
                           self._aergo2, self._aergo1,
                           self._addr2, self._addr1, False)
        t_mainnet = threading.Thread(target=self.bridge_worker,
                                     args=from_mainnet_args)
        t_sidechain = threading.Thread(target=self.bridge_worker,
                                       args=to_mainnet_args)
        t_mainnet.start()
        t_sidechain.start()
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            print("\nInitiating proposer shutdown")
            self.kill_proposer_threads = True
            t_mainnet.join()
            t_sidechain.join()
            self.shutdown()

    def bridge_worker(self, t_anchor_to, t_final_from,
                      aergo_from, aergo_to, bridge_from, bridge_to,
                      is_from_mainnet, tab=""):
        while True:
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
                  "{0}| last merged height : {1}\n"
                  "{0}| last merged contract trie root :{2}...\n"
                  "{0}| current update nonce: {3}\n"
                  .format(tab, merged_height_from,
                          merged_root_from[:20], nonce_to))

            while True:
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
                        self.get_validators_signatures(anchor_msg, tab)
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

            # TODO don't broadcast if somebody else already did
            # Broadcast finalised merge block
            tx, result = aergo_to.call_sc(bridge_to, "set_root",
                                          args=[root, next_anchor_height,
                                                validator_indexes,
                                                sigs])
            if result.status != herapy.CommitStatus.TX_OK:
                print("{}Anchor on aergo Tx commit failed : {}"
                      .format(tab, result))
                return

            time.sleep(COMMIT_TIME)
            result = aergo_to.get_tx_result(tx.tx_hash)
            # TODO handle result not success for example somebody else already
            # set_root
            if result.status != herapy.TxResultStatus.SUCCESS:
                print("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address,
                              result.status, result.detail))
                return

            # Wait t_anchor
            print("{0}anchor success,\n{0}waiting new anchor time : {1}s ..."
                  .format(tab, t_anchor_to-COMMIT_TIME))
            if self.kill_proposer_threads:
                print("{}stopping thread".format(tab))
                return
            time.sleep(t_anchor_to-COMMIT_TIME)

    def shutdown(self):
        print("\nDisconnecting AERGO")
        self._aergo1.disconnect()
        self._aergo2.disconnect()
        print("Closing channels")
        for channel in self._channels:
            channel.close()


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    proposer = ProposerClient(config_data, 'mainnet', 'sidechain2')
    proposer.run()
