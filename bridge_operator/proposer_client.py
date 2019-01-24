import grpc
import hashlib
import json
import time

import aergo.herapy as herapy
import bridge_operator_pb2_grpc
import bridge_operator_pb2


COMMIT_TIME = 3


class ProposerClient:
    """The bridge proposer periodically (every t_anchor) broadcasts the finalized
    trie state root (after t_final) of the bridge contract on both sides of the
    bridge after validation by the Validator servers.
    It first checks the last merged height and waits until
    now + t_anchor + t_final is reached, then merges the current finalised
    block (now - t_final). Start again after waiting t_anchor.
    """

    def __init__(self):
        with open("./config.json", "r") as f:
            config_data = json.load(f)
        with open("./bridge_operator/bridge_addresses.txt", "r") as f:
            self._addr1 = f.readline()[:52]
            self._addr2 = f.readline()[:52]
        # TODO use and array to store multiple channels
        self._channel = grpc.insecure_channel('localhost:9841')
        self._stub = bridge_operator_pb2_grpc.BridgeOperatorStub(self._channel)

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
        sender_priv_key1 = config_data['priv_key']["proposer"]
        sender_priv_key2 = config_data['priv_key']["proposer"]
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        self._aergo2.new_account(private_key=sender_priv_key2)
        self._aergo1.get_account()
        self._aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

    def get_validators_signatures(self, root1, merge_height1, nonce2, root2, merge_height2, nonce1):
        anchor1 =  bridge_operator_pb2.Anchor(origin_root=root1,
                                            origin_height=str(merge_height1),
                                            nonce=str(nonce2))
        anchor2 =  bridge_operator_pb2.Anchor(origin_root=root2,
                                            origin_height=str(merge_height2),
                                            nonce=str(nonce1))
        proposal = bridge_operator_pb2.Proposals(anchor1=anchor1,
                                                anchor2=anchor2)
        # get validator signatures
        approval = self._stub.GetAnchorSignature(proposal)

        # TODO verify received signatures of h1 and h2
        msg1 = bytes(root1 + str(merge_height1) + str(nonce2), 'utf-8')
        msg2 = bytes(root2 + str(merge_height2) + str(nonce1), 'utf-8')
        h1 = hashlib.sha256(msg1).digest()
        h2 = hashlib.sha256(msg2).digest()

        print(approval)
        return [approval.sig1], [approval.sig2]

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
                print(" __\n| last merged heights :", merged_height1, merged_height2)
                print("| last merged contract trie roots:", merged_root1[:20] + b'..."',
                    merged_root2[:20] + b'..."')
                print("| current update nonces:", nonce1, nonce2)

                # Wait for the next anchor time
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

                # Calculate finalised block height and root to broadcast
                merge_height1 = best_height1 - self._t_final
                merge_height2 = best_height2 - self._t_final
                block1 = self._aergo1.get_block(block_height=merge_height1)
                block2 = self._aergo2.get_block(block_height=merge_height2)
                contract1 = self._aergo1.get_account(address=self._addr1, proof=True,
                                            root=block1.blocks_root_hash)
                contract2 = self._aergo2.get_account(address=self._addr2, proof=True,
                                            root=block2.blocks_root_hash)
                root1 = contract1.state_proof.state.storageRoot.hex()
                root2 = contract2.state_proof.state.storageRoot.hex()
                if len(root1) == 0 or len(root2) == 0:
                    print("waiting deployment finalization...")
                    time.sleep(self._t_final/4)
                    continue

                print("anchoring new roots :", '"0x' + root1[:17] + '..."', '"0x' + root2[:17] + '..."')
                print("Gathering signatures from validators ...")
                sigs1, sigs2 = self.get_validators_signatures(root1, merge_height1, nonce2, root2, merge_height2, nonce1)

                # Broadcast finalised merge block
                tx2, result2 = self._aergo2.call_sc(self._addr2, "set_root",
                                            args=[root1, merge_height1,
                                                    [1], sigs1])
                tx1, result1 = self._aergo1.call_sc(self._addr1, "set_root",
                                            args=[root2, merge_height2,
                                                    [1], sigs2])

                time.sleep(COMMIT_TIME)
                result1 = self._aergo1.get_tx_result(tx1.tx_hash)
                if result1.status != herapy.SmartcontractStatus.SUCCESS:
                    print("  > ERROR[{0}]:{1}: {2}".format(
                        result1.contract_address, result1.status, result1.detail))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return
                result2 = self._aergo2.get_tx_result(tx2.tx_hash)
                if result2.status != herapy.SmartcontractStatus.SUCCESS:
                    print("  > ERROR[{0}]:{1}: {2}".format(
                        result2.contract_address, result2.status, result2.detail))
                    self._aergo1.disconnect()
                    self._aergo2.disconnect()
                    return

                # Waite t_anchor
                print("anchor success, waiting new anchor time :", self._t_anchor-COMMIT_TIME, "s ...")
                time.sleep(self._t_anchor-COMMIT_TIME)

        except grpc.RpcError as e:
            print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                    e.details()))
        except KeyboardInterrupt:
            print("Shutting down proposer")

        self.shutdown()

    def shutdown(self):
        print("------ Disconnect AERGO -----------")
        self._aergo1.disconnect()
        self._aergo2.disconnect()
        # TODO disconnect channels



if __name__ == '__main__':
    proposer = ProposerClient()
    proposer.run()
