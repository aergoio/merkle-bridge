import grpc
import time
import json
import hashlib

import aergo.herapy as herapy
import base58

# The bridge operator periodically (every t_anchor) broadcasts the finalized
# trie state root (after t_final) of the bridge contract on both sides of the
# bridge.
# It first checks the last merged height and waits until
# now + t_anchor + t_final is reached, then merges the current finalised
# block (now - t_final). Start again after waiting t_anchor.


def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    t_anchor = config_data['t_anchor']
    t_final = config_data['t_final']
    print(" * anchoring periode : ", t_anchor, "s\n",
          "* chain finality periode : ", t_final, "s\n")
    f.close()
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['aergo1']['ip'])
        aergo2.connect(config_data['aergo2']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data['aergo1']['priv_key']
        sender_priv_key2 = config_data['aergo2']['priv_key']
        sender_account = aergo1.new_account(password="test",
                                            private_key=sender_priv_key1)
        aergo2.new_account(password="test",
                           private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))
        print("------ START BRIDGE OPERATOR -----------")

        while True:
            print("----------------- ANCHOR NEW ROOTS -----------------")
            # Get current merge block height
            height_proof_1 = aergo1.query_sc_state(addr1, "Height")
            height_proof_2 = aergo2.query_sc_state(addr2, "Height")
            root_proof_1 = aergo1.query_sc_state(addr1, "Root")
            root_proof_2 = aergo2.query_sc_state(addr2, "Root")
            merged_height1 = int(height_proof_1.var_proof.var_proof.value)
            merged_height2 = int(height_proof_2.var_proof.var_proof.value)
            merged_root1 = root_proof_1.var_proof.var_proof.value
            merged_root2 = root_proof_2.var_proof.var_proof.value
            print("last merged heights :", merged_height1, merged_height2)
            print("last merged contract trie roots:", merged_root1,
                  merged_root2)

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
                print("waiting new anchor time :", -longest_wait, "s")
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
            root1 = contract1.state_proof.state.storageRoot
            root2 = contract2.state_proof.state.storageRoot
            root1 = base58.b58encode(root1).decode('utf-8')
            root2 = base58.b58encode(root2).decode('utf-8')
            if len(root1) == 0 or len(root2) == 0:
                print("waiting deployment finalization...")
                time.sleep(t_final/4)
                continue
            print("anchoring new roots :", root1, root2)

            # Sign root and height update
            msg1 = bytes(root1 + str(merge_height1), 'utf-8')
            msg2 = bytes(root2 + str(merge_height2), 'utf-8')
            h1 = hashlib.sha256(msg1).digest()
            h2 = hashlib.sha256(msg2).digest()
            sig1 = aergo1.account.private_key.sign_msg(h1).hex()
            sig2 = aergo2.account.private_key.sign_msg(h2).hex()

            # Broadcast finalised merge block
            tx1, result1 = aergo1.call_sc(addr1, "set_root",
                                          args=[root1, merge_height1,
                                                [1], [sig1]])
            tx2, result2 = aergo2.call_sc(addr2, "set_root",
                                          args=[root2, merge_height2,
                                                [1], [sig2]])

            confirmation_time = 3
            time.sleep(confirmation_time)
            result1 = aergo1.get_tx_result(tx1.tx_hash)
            if result1.status != herapy.SmartcontractStatus.SUCCESS:
                print("  > ERROR[{0}]:{1}: {2}".format(
                    result1.contract_address, result1.status, result1.detail))
                aergo1.disconnect()
                aergo2.disconnect()
                return
            result2 = aergo2.get_tx_result(tx2.tx_hash)
            if result2.status != herapy.SmartcontractStatus.SUCCESS:
                print("  > ERROR[{0}]:{1}: {2}".format(
                    result2.contract_address, result2.status, result2.detail))
                aergo1.disconnect()
                aergo2.disconnect()
                return

            # Waite t_anchor
            print("waiting new anchor time :", t_anchor-confirmation_time, "s")
            time.sleep(t_anchor-3)

    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                  e.details()))
    except KeyboardInterrupt:
        print("Shutting down operator")

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    run()
