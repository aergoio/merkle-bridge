import grpc
import hashlib
import json
import time

import aergo.herapy as herapy

# The bridge operator periodically (every t_anchor) broadcasts the finalized
# trie state root (after t_final) of the bridge contract on both sides of the
# bridge.
# It first checks the last merged height and waits until
# now + t_anchor + t_final is reached, then merges the current finalised
# block (now - t_final). Start again after waiting t_anchor.

COMMIT_TIME = 3


def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    addr1 = config_data['mainnet']['bridges']['sidechain2']
    addr2 = config_data['sidechain2']['bridges']['mainnet']
    t_anchor = config_data['t_anchor']
    t_final = config_data['t_final']
    print(" * anchoring periode : ", t_anchor, "s\n",
          "* chain finality periode : ", t_final, "s\n")
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['mainnet']['ip'])
        aergo2.connect(config_data['sidechain2']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data["proposer"]['priv_key']
        sender_priv_key2 = config_data["proposer"]['priv_key']
        sender_account = aergo1.new_account(private_key=sender_priv_key1)
        aergo2.new_account(private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))
        print("------ START BRIDGE OPERATOR -----------")

        while True:
            # Get current merge block height
            merge_info1 = aergo1.query_sc_state(addr1,
                                                ["_sv_Height",
                                                 "_sv_Root",
                                                 "_sv_Nonce"
                                                 ])
            merge_info2 = aergo2.query_sc_state(addr2,
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
            print("| last merged contract trie roots:",
                  merged_root1[:20] + b'..."',
                  merged_root2[:20] + b'..."')
            print("| current update nonces:", nonce1, nonce2)

            # Wait for the next anchor time
            while True:
                # Get origin and destination best height
                _, best_height1 = aergo1.get_blockchain_status()
                _, best_height2 = aergo2.get_blockchain_status()

                # Waite best height - t_final >= merge block height + t_anchor
                wait1 = best_height1 - t_final - (merged_height1 + t_anchor)
                wait2 = best_height2 - t_final - (merged_height2 + t_anchor)
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

            # Calculate finalised block to broadcast
            merge_height1 = best_height1 - t_final
            merge_height2 = best_height2 - t_final
            block1 = aergo1.get_block(block_height=merge_height1)
            block2 = aergo2.get_block(block_height=merge_height2)
            contract1 = aergo1.get_account(address=addr1, proof=True,
                                           root=block1.blocks_root_hash)
            contract2 = aergo2.get_account(address=addr2, proof=True,
                                           root=block2.blocks_root_hash)
            root1 = contract1.state_proof.state.storageRoot.hex()
            root2 = contract2.state_proof.state.storageRoot.hex()
            if len(root1) == 0 or len(root2) == 0:
                print("waiting deployment finalization...")
                time.sleep(t_final/4)
                continue

            print("anchoring new roots : '0x{}...', '0x{}'..."
                  .format(root1[:17], root2[:17]))
            # Sign root and height update
            msg1 = bytes(root1 + str(merge_height1) + str(nonce2), 'utf-8')
            msg2 = bytes(root2 + str(merge_height2) + str(nonce1), 'utf-8')
            h1 = hashlib.sha256(msg1).digest()
            h2 = hashlib.sha256(msg2).digest()
            sig1 = "0x" + aergo2.account.private_key.sign_msg(h1).hex()
            sig2 = "0x" + aergo1.account.private_key.sign_msg(h2).hex()

            # Broadcast finalised merge block
            tx2, result2 = aergo2.call_sc(addr2, "set_root",
                                          args=[root1, merge_height1,
                                                [1], [sig1]])
            tx1, result1 = aergo1.call_sc(addr1, "set_root",
                                          args=[root2, merge_height2,
                                                [1], [sig2]])

            time.sleep(COMMIT_TIME)
            result1 = aergo1.get_tx_result(tx1.tx_hash)
            if result1.status != herapy.SmartcontractStatus.SUCCESS:
                print("  > ERROR[{0}]:{1}: {2}"
                      .format(result1.contract_address, result1.status,
                              result1.detail))
                aergo1.disconnect()
                aergo2.disconnect()
                return
            result2 = aergo2.get_tx_result(tx2.tx_hash)
            if result2.status != herapy.SmartcontractStatus.SUCCESS:
                print("  > ERROR[{0}]:{1}: {2}"
                      .format(result2.contract_address, result2.status,
                              result2.detail))
                aergo1.disconnect()
                aergo2.disconnect()
                return

            # Waite t_anchor
            print("anchor success, waiting new anchor time :", t_anchor-COMMIT_TIME, "s ...")
            time.sleep(t_anchor-COMMIT_TIME)

    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'
              .format(e.code(), e.details()))
    except KeyboardInterrupt:
        print("Shutting down operator")

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    run()
