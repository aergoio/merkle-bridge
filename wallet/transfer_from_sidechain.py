import grpc
import json
import time

import aergo.herapy as herapy


def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    with open("./wallet/token_mint_address.txt", "r") as f:
        token_mint = f.readline()[:52]
    with open("./wallet/token_address.txt", "r") as f:
        token_origin = f.readline()[:52]
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

        print("------ Burn tokens -----------")
        # get current balance and nonce
        initial_state = aergo2.query_sc_state(token_mint,
                                          ["_sv_Balances-" +
                                           sender_account.address.__str__(),
                                           "_sv_Nonces-" +
                                           sender_account.address.__str__(),
                                           "_sv_ContractID"
                                          ])
        balance_p, nonce_p, contractID_p = [item.value for item in initial_state.var_proofs]
        balance = int(json.loads(balance_p)["_bignum"])
        try:
            nonce= int(json.loads(nonce_p)["_bignum"])
        except ValueError:
            nonce = 0
        print("Token address in sidechain : ", token_mint)
        print("Token balance in sidechain contract : ", balance,
              "    nonce : ", nonce)

        # record current lock balance
        account_ref = sender_account.address.__str__() + token_origin
        burn_p = aergo2.query_sc_state(addr2, ["_sv_Burns-" + account_ref])
        try:
            burn_before = int(burn_p.var_proofs[0].value[1:-1])
        except ValueError:
            burn_before = 0
        print("Current burnt balance : ", burn_before)

        # lock and check block height of lock tx
        to = sender_account.address.__str__()
        value = 5
        tx, result = aergo2.call_sc(addr2, "burn",
                                    args=[to, str(value), token_mint])
        confirmation_time = 3
        time.sleep(confirmation_time)
        _, burn_height = aergo2.get_blockchain_status()
        result = aergo2.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("New burnt balance : ", result.detail)

        print("------ Wait finalisation and get burn proof -----------")
        # check current merged height at destination
        height_proof_1 = aergo1.query_sc_state(addr2, ["_sv_Height"])
        merged_height1 = int(height_proof_1.var_proofs[0].value)
        print("last merged height at destination :", merged_height1)
        # wait t_final
        print("waiting finalisation :", t_final-confirmation_time, "s...")
        time.sleep(t_final)
        # check last merged height
        height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
        last_merged_height1 = int(height_proof_1.var_proofs[0].value)
        # waite for anchor containing our transfer
        while last_merged_height1 < burn_height:
            print("waiting new anchor...")
            time.sleep(t_anchor/4)
            height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
            last_merged_height1 = int(height_proof_1.var_proofs[0].value)
            # TODO do this with events when available
        # get inclusion proof of lock in last merged block
        merge_block2 = aergo2.get_block(block_height=last_merged_height1)
        burn_proof = aergo2.query_sc_state(addr2, ["_sv_Burns-" + account_ref],
                                           root=merge_block2.blocks_root_hash,
                                           compressed=False)
        if not burn_proof.verify_proof(merge_block2.blocks_root_hash):
            print("Unable to verify lock proof")
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print(burn_proof)
        print("------ Unlock tokens on destination blockchain -----------")
        receiver = sender_account.address.__str__()
        balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
        auditPath = burn_proof.var_proofs[0].auditPath
        ap = [node.hex() for node in auditPath]
        print(ap)
        # call mint on aergo2 with the lock proof from aergo1
        tx, result = aergo1.call_sc(addr1, "unlock",
                                    args=[receiver, balance,
                                          token_origin, ap])
        time.sleep(confirmation_time)
        result = aergo1.get_tx_result(tx.tx_hash)
        origin_address = result.detail[1:-1]
        print("Token's address on origin: ", origin_address)
        burnt_balance = aergo2.query_sc_state(token_mint,
                                          ["_sv_Balances-" +
                                           sender_account.address.__str__(),
                                          ])
        print(burnt_balance)
        # remaining balance on sidechain
        balance = json.loads(burnt_balance.var_proofs[0].value)
        print("New token balance on sidechain: ", balance)

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
