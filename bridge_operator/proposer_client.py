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
    BridgeOperatorStub,
)
from bridge_operator.bridge_operator_pb2 import (
    Anchor,
    Proposals,
)


COMMIT_TIME = 3


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
        self._addr1 = config_data[aergo1]['bridges'][aergo2]
        self._addr2 = config_data[aergo2]['bridges'][aergo1]

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

        self._t_anchor = self._config_data['t_anchor']
        self._t_final = self._config_data['t_final']
        print(" * anchoring periode : ", self._t_anchor, "s\n",
              "* chain finality periode : ", self._t_final, "s\n")

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(self._config_data[aergo1]['ip'])
        self._aergo2.connect(self._config_data[aergo2]['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = self._config_data["proposer"]['priv_key']
        sender_priv_key2 = self._config_data["proposer"]['priv_key']
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        self._aergo2.new_account(private_key=sender_priv_key2)
        self._aergo1.get_account()
        self._aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

    def get_validators_signatures(self, anchor_msg1, anchor_msg2):
        root1, merge_height1, nonce2 = anchor_msg1
        root2, merge_height2, nonce1 = anchor_msg2
        anchor1 = Anchor(root=root1,
                         height=str(merge_height1),
                         destination_nonce=str(nonce2))
        anchor2 = Anchor(root=root2,
                         height=str(merge_height2),
                         destination_nonce=str(nonce1))
        proposal = Proposals(anchor1=anchor1, anchor2=anchor2)
        # get validator signatures
        validator_indexes = [i for i in range(len(self._stubs))]
        worker = partial(self.get_signature_worker, proposal)
        approvals = self._pool.map(worker, validator_indexes)
        sigs1, sigs2, validator_indexes = self.extract_signatures(approvals)

        msg1 = bytes(root1 + str(merge_height1) + str(nonce2), 'utf-8')
        msg2 = bytes(root2 + str(merge_height2) + str(nonce1), 'utf-8')
        h1 = hashlib.sha256(msg1).digest()
        h2 = hashlib.sha256(msg2).digest()

        return sigs1, sigs2, validator_indexes

    def get_signature_worker(self, proposal, index):
        try:
            approval = self._stubs[index].GetAnchorSignature(proposal)
            # TODO verify signatures: check approval.address ==
            # validators[index] and check sig
        except grpc.RpcError as e:
            return None
        return approval

    def extract_signatures(self, approvals):
        sigs1, sigs2, validator_indexes = [], [], []
        for i, approval in enumerate(approvals):
            if approval is not None:
                sigs1.append(approval.sig1)
                sigs2.append(approval.sig2)
                validator_indexes.append(i+1)
        if 3 * len(sigs1) < 2 * len(self._config_data['validators']):
            raise ValidatorMajorityError()
        # slice 2/3 of total validator
        two_thirds = ((len(self._stubs) * 2) // 3
                      + ((len(self._stubs) * 2) % 3 > 0))
        return sigs1[:two_thirds], sigs2[:two_thirds], validator_indexes[:two_thirds]

    def wait_for_next_anchor(self, merged_height1, merged_height2):
        while True:
            # Get origin and destination best height
            _, best_height1 = self._aergo1.get_blockchain_status()
            _, best_height2 = self._aergo2.get_blockchain_status()

            # Waite best height - t_final >= merge block height + t_anchor
            wait1 = best_height1 - self._t_final - (merged_height1 + self._t_anchor)
            wait2 = best_height2 - self._t_final - (merged_height2 + self._t_anchor)
            if wait1 >= 0 and wait2 >= 0:
                break
            # choose the longest time to wait.
            longest_wait = 0
            if wait1 < longest_wait:
                longest_wait = wait1
            if wait2 < longest_wait:
                longest_wait = wait2
            print("waiting new anchor time :", -longest_wait, "s ...")
            time.sleep(-longest_wait)
        return best_height1, best_height2

    def run(self):
        try:
            print("------ START BRIDGE OPERATOR -----------")
            while True:

                # Get last merge information
                merge_info1 = self._aergo1.query_sc_state(self._addr1,
                                                          ["_sv_Height",
                                                           "_sv_Root",
                                                           "_sv_Nonce"
                                                           ])
                merge_info2 = self._aergo2.query_sc_state(self._addr2,
                                                          ["_sv_Height",
                                                           "_sv_Root",
                                                           "_sv_Nonce"
                                                           ])
                merged_height2, merged_root2, nonce1 = [proof.value for proof in merge_info1.var_proofs]
                merged_height2 = int(merged_height2)
                nonce1 = int(nonce1)

                merged_height1, merged_root1, nonce2 = [proof.value for proof in merge_info2.var_proofs]
                merged_height1 = int(merged_height1)
                nonce2 = int(nonce2)
                print(" __\n| last merged heights :",
                      merged_height1, merged_height2)
                print("| last merged contract trie roots: {}..., {}..."
                      .format(merged_root1[:20], merged_root2[:20]))
                print("| current update nonces:", nonce1, nonce2)

                while True:
                    # Wait for the next anchor time
                    best_height1, best_height2 = self.wait_for_next_anchor(merged_height1,
                                                                           merged_height2)

                    # Calculate finalised block height and root to broadcast
                    merge_height1 = best_height1 - self._t_final
                    merge_height2 = best_height2 - self._t_final
                    block1 = self._aergo1.get_block(block_height=merge_height1)
                    block2 = self._aergo2.get_block(block_height=merge_height2)
                    contract1 = self._aergo1.get_account(address=self._addr1,
                                                         proof=True,
                                                         root=block1.blocks_root_hash)
                    contract2 = self._aergo2.get_account(address=self._addr2,
                                                         proof=True,
                                                         root=block2.blocks_root_hash)
                    root1 = contract1.state_proof.state.storageRoot.hex()
                    root2 = contract2.state_proof.state.storageRoot.hex()
                    if len(root1) == 0 or len(root2) == 0:
                        print("waiting deployment finalization...")
                        time.sleep(self._t_final/4)
                        continue

                    print("anchoring new roots :'0x{}...', '0x{}...'"
                          .format(root1[:17], root2[:17]))
                    print("Gathering signatures from validators ...")

                    try:
                        anchor_msg1 = root1, merge_height1, nonce2
                        anchor_msg2 = root2, merge_height2, nonce1
                        sigs1, sigs2, validator_indexes = self.get_validators_signatures(anchor_msg1,
                                                                                         anchor_msg2)
                    except ValidatorMajorityError:
                        print("Failed to gather 2/3 validators signatures, waiting for next anchor...")
                        time.sleep(self._t_anchor)
                        continue
                    break

                # Broadcast finalised merge block
                tx2, result2 = self._aergo2.call_sc(self._addr2, "set_root",
                                                    args=[root1, merge_height1,
                                                          validator_indexes,
                                                          sigs1])
                tx1, result1 = self._aergo1.call_sc(self._addr1, "set_root",
                                                    args=[root2, merge_height2,
                                                          validator_indexes,
                                                          sigs2])
                if result2.status != herapy.CommitStatus.TX_OK:
                    print("Deploy bridge aergo2 Tx commit failed : {}".format(result2))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return
                if result1.status != herapy.CommitStatus.TX_OK:
                    print("Deploy bridge aergo1 Tx commit failed : {}".format(result1))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return

                time.sleep(COMMIT_TIME)
                result1 = self._aergo1.get_tx_result(tx1.tx_hash)
                if result1.status != herapy.TxResultStatus.SUCCESS:
                    print("  > ERROR[{0}]:{1}: {2}"
                          .format(result1.contract_address, result1.status, result1.detail))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return
                result2 = self._aergo2.get_tx_result(tx2.tx_hash)
                if result2.status != herapy.TxResultStatus.SUCCESS:
                    print("  > ERROR[{0}]:{1}: {2}"
                          .format(result2.contract_address, result2.status, result2.detail))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return

                # Wait t_anchor
                print("anchor success, waiting new anchor time :", self._t_anchor-COMMIT_TIME, "s ...")
                time.sleep(self._t_anchor-COMMIT_TIME)

        except KeyboardInterrupt:
            print("Shutting down proposer")
            self.shutdown()

    def shutdown(self):
        print("------ Disconnect AERGO -----------")
        self._aergo1.disconnect()
        self._aergo2.disconnect()
        for channel in self._channels:
            channel.close()


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    proposer = ProposerClient(config_data, 'mainnet', 'sidechain2')
    proposer.run()
