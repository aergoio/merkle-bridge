import grpc
import json
import hashlib
import time
import sys

import aergo.herapy as herapy

def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    with open("./wallet/token_address.txt", "r") as f:
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

        # Get bridge information
        bridge_info = aergo1.query_sc_state(addr1,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                            ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")

        # get current balance and nonce
        initial_state = aergo1.query_sc_state(token,
                                          ["_sv_Balances-" +
                                           sender_account.address.__str__(),
                                           "_sv_Nonces-" +
                                           sender_account.address.__str__(),
                                           "_sv_ContractID"
                                          ])
        balance_p, nonce_p, contractID_p = [item.value for item in initial_state.var_proofs]
        balance = int(json.loads(balance_p)["_bignum"])
        try:
            nonce= int(nonce_p)
        except ValueError:
            nonce = 0
        print("Token address : ", token)
        print("Balance on origin: ", balance)


        print("\n------ Lock tokens -----------")
        # make a signed transfer of 5 tokens
        to = sender_account.address.__str__()
        value = 5
        fee = 0
        deadline = 0
        contractID = str(contractID_p[1:-1], 'utf-8')
        msg = bytes(addr1 + str(value) + str(nonce) + str(fee) +
                    str(deadline) + contractID, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = aergo1.account.private_key.sign_msg(h).hex()

        # lock and check block height of lock tx
        print("Transfering", value, "tokens...")
        tx, result = aergo1.call_sc(addr1, "lock",
                                    args=[to, str(value), token, nonce, sig])
        commit_time = 3
        time.sleep(commit_time)
        # Record lock height
        _, lock_height = aergo1.get_blockchain_status()
        # Check lock success
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("Lock success : ", result.detail)

        print("------ Wait finalisation and get lock proof -----------")
        # check current merged height at destination
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        merged_height2 = int(height_proof_2.var_proofs[0].value)
        print("last merged height at destination :", merged_height2)
        # wait t_final
        print("waiting finalisation :", t_final-commit_time, "s...")
        time.sleep(t_final)
        # check last merged height
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        last_merged_height2 = int(height_proof_2.var_proofs[0].value)
        # waite for anchor containing our transfer
        sys.stdout.write("waiting new anchor ")
        while last_merged_height2 < lock_height:
            sys.stdout.flush()
            sys.stdout.write(". ")
            time.sleep(t_anchor/4)
            height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
            last_merged_height2 = int(height_proof_2.var_proofs[0].value)
            # TODO do this with events when available
        # get inclusion proof of lock in last merged block
        merge_block1 = aergo1.get_block(block_height=last_merged_height2)
        account_ref = sender_account.address.__str__() + token
        lock_proof = aergo1.query_sc_state(addr1, ["_sv_Locks-" + account_ref],
                                           root=merge_block1.blocks_root_hash,
                                           compressed=False)
        if not lock_proof.verify_proof(merge_block1.blocks_root_hash):
            print("Unable to verify lock proof")
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("\n------ Mint tokens on destination blockchain -----------")
        receiver = sender_account.address.__str__()
        balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
        auditPath = lock_proof.var_proofs[0].auditPath
        ap = [node.hex() for node in auditPath]
        token_origin = token
        # call mint on aergo2 with the lock proof from aergo1
        tx, result = aergo2.call_sc(addr2, "mint",
                                    args=[receiver, balance,
                                          token_origin, ap])
        time.sleep(commit_time)
        result = aergo2.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("Mint success on sidechain : ", result.detail)

        mint_address = json.loads(result.detail)[0]
        minted_balance = aergo2.query_sc_state(mint_address,
                                          ["_sv_Balances-" +
                                           sender_account.address.__str__(),
                                          ])
        # check newly minted balance
        balance = json.loads(minted_balance.var_proofs[0].value)
        print("Pegged contract address on sidechain :", mint_address)
        print("Balance on sidechain : ", balance)
        origin_balance = aergo1.query_sc_state(token_origin,
                                          ["_sv_Balances-" +
                                           sender_account.address.__str__(),
                                          ])
        # remaining balance on sidechain
        balance = json.loads(origin_balance.var_proofs[0].value)
        print("Balance on origin: ", balance)



        # record mint address in file
        with open("./wallet/token_mint_address.txt", "w") as f:
            f.write(mint_address)
            f.write("_MINT_TOKEN_1\n")

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
