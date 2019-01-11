import grpc
import json
import hashlib
import time

import aergo.herapy as herapy


def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    with open("./bridge_operator/token_address.txt", "r") as f:
        token = f.readline()[:52]
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['aergo1']['ip'])
        aergo2.connect(config_data['aergo2']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data['priv_key']["wallet"]
        sender_priv_key2 = config_data['priv_key']["wallet"]
        sender_account = aergo1.new_account(private_key=sender_priv_key1)
        aergo2.new_account(private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: ", sender_account.address.__str__())

        t_anchor_p = aergo1.query_sc_state(addr1, ["_sv_T_anchor"])
        t_final_p = aergo1.query_sc_state(addr1, ["_sv_T_final"])
        t_anchor = int(t_anchor_p.var_proof.var_proof[0].value)
        t_final = int(t_final_p.var_proof.var_proof[0].value)

        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")

        print("------ Lock tokens -----------")
        # get current balance and nonce
        print(type(sender_account.address))
        balance_p = aergo1.query_sc_state(token, ["_sv_Balances-" +
                                                  sender_account.address.__str__()])
        nonce_p = aergo1.query_sc_state(token, ["_sv_Nonces-" +
                                        sender_account.address.__str__()])
        balance = int(balance_p.var_proof.var_proof[0].value)
        try:
            nonce = int(nonce_p.var_proof.var_proof[0].value)
        except ValueError:
            nonce = 0
        print("Token address : ", token)
        print("Token balance in origin contract : ", balance,
              "    nonce : ", nonce)

        # record current lock balance
        account_ref = sender_account.address.__str__() + token
        lock_p = aergo1.query_sc_state(addr1, ["_sv_Locks-" + account_ref])
        try:
            lock_before = int(lock_p.var_proof.var_proof[0].value)
        except ValueError:
            lock_before = 0
        print("Current locked balance : ", lock_before)

        # make a signed transfer of 5 tokens
        to = sender_account.address.__str__()
        value = 5
        fee = 0
        deadline = 0
        # Get the contract's id
        contractID_p = aergo1.query_sc_state(token, ["_sv_ContractID"])
        contractID = str(contractID_p.var_proof.var_proof[0].value[1:-1], 'utf-8')
        msg = bytes(addr1 + str(value) + str(nonce) + str(fee) +
                    str(deadline) + contractID, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = aergo1.account.private_key.sign_msg(h).hex()

        # lock and check block height of lock tx
        tx, result = aergo1.call_sc(addr1, "lock",
                                    args=[to, value, token, nonce, sig])
        confirmation_time = 3
        time.sleep(confirmation_time)
        _, lock_height = aergo1.get_blockchain_status()
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("New locked balance : ", result.detail)

        print("------ Wait finalisation and get lock proof -----------")
        # check current merged height at destination
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        merged_height2 = int(height_proof_2.var_proof.var_proof[0].value)
        print("last merged height at destination :", merged_height2)
        # wait t_final
        print("waiting finalisation :", t_final-confirmation_time, "s...")
        time.sleep(t_final)
        # check last merged height
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        last_merged_height2 = int(height_proof_2.var_proof.var_proof[0].value)
        # waite for anchor containing our transfer
        while last_merged_height2 < lock_height:
            print("waiting new anchor...")
            time.sleep(t_anchor/4)
            height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
            last_merged_height2 = int(height_proof_2.var_proof.var_proof[0].value)
            # TODO do this with events when available
        # get inclusion proof of lock in last merged block
        merge_block1 = aergo1.get_block(block_height=last_merged_height2)
        lock_proof = aergo1.query_sc_state(addr1, ["_sv_Locks-" + account_ref],
                                           root=merge_block1.blocks_root_hash,
                                           compressed=False)
        if not lock_proof.verify_proof(merge_block1.blocks_root_hash):
            print("Unable to verify lock proof")
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print(lock_proof)
        print("------ Mint tokens on destination blockchain -----------")
        receiver = sender_account.address.__str__()
        balance = int(lock_proof.var_proof.var_proof[0].value)
        auditPath = lock_proof.var_proof.var_proof[0].auditPath
        ap = [node.hex() for node in auditPath]
        token_origin = token
        print(ap)
        # call mint on aergo2 with the lock proof from aergo1
        tx, result = aergo2.call_sc(addr2, "mint",
                                    args=[receiver, balance,
                                          token_origin, ap])
        time.sleep(confirmation_time)
        result = aergo2.get_tx_result(tx.tx_hash)
        print(result)
        # TODO this requires contract deployment from within contract support by
        # lua
        # check newly minted balance

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
