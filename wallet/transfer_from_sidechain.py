import grpc
import json
import sys
import time

import aergo.herapy as herapy

COMMIT_TIME = 3


def burn(aergo2, receiver, addr2, token_pegged):
    # lock and check block height of lock tx
    value = 8*10**18
    print("Transfering", value/10**18, "tokens...")
    tx, result = aergo2.call_sc(addr2, "burn",
                                args=[receiver, str(value), token_pegged])
    time.sleep(COMMIT_TIME)
    # Record burn height
    _, burn_height = aergo2.get_blockchain_status()
    # Check burn success
    result = aergo2.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        print("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
        return None, False
    print("Burn success : ", result.detail)
    return burn_height, True


def build_burn_proof(aergo1, aergo2, receiver, addr1, addr2, burn_height,
                     token_origin, t_anchor, t_final):
    # check current merged height at destination
    height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
    merged_height1 = int(height_proof_1.var_proofs[0].value)
    print("last merged height at destination :", merged_height1)
    # wait t_final
    print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
    time.sleep(t_final)
    # check last merged height
    height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
    last_merged_height1 = int(height_proof_1.var_proofs[0].value)
    # waite for anchor containing our transfer
    sys.stdout.write("waiting new anchor ")
    while last_merged_height1 < burn_height:
        sys.stdout.flush()
        sys.stdout.write(". ")
        time.sleep(t_anchor/4)
        height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
        last_merged_height1 = int(height_proof_1.var_proofs[0].value)
        # TODO do this with events when available
    # get inclusion proof of lock in last merged block
    merge_block2 = aergo2.get_block(block_height=last_merged_height1)
    account_ref = receiver + token_origin
    burn_proof = aergo2.query_sc_state(addr2, ["_sv_Burns-" + account_ref],
                                       root=merge_block2.blocks_root_hash,
                                       compressed=False)
    if not burn_proof.verify_proof(merge_block2.blocks_root_hash):
        print("Unable to verify burn proof")
        return None, False
    return burn_proof, True


def unlock(aergo1, receiver, burn_proof, token_origin, addr1):
    balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = burn_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo2 with the lock proof from aergo1
    tx, result = aergo1.call_sc(addr1, "unlock",
                                args=[receiver, balance,
                                      token_origin, ap])
    time.sleep(COMMIT_TIME)
    result = aergo1.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        print("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
        return False

    print("Unlock success on origin : ", result.detail)
    return True


def run(aer=False):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    addr1 = config_data['aergo1']['bridges']['aergo2']
    addr2 = config_data['aergo2']['bridges']['aergo1']
    token_pegged = config_data['aergo1']['tokens']['token1']['pegs']['aergo2']
    token_origin = config_data['aergo1']['tokens']['token1']['addr']
    if aer:
        token_origin = "aergo"
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['aergo1']['ip'])
        aergo2.connect(config_data['aergo2']['ip'])

        sender_priv_key1 = config_data["wallet"]['priv_key']
        sender_priv_key2 = config_data["wallet"]['priv_key']
        sender_account = aergo1.new_account(private_key=sender_priv_key1)
        aergo2.new_account(private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()

        sender = sender_account.address.__str__()
        receiver = sender
        print("  > Sender Address: ", sender)

        # Get bridge information
        bridge_info = aergo1.query_sc_state(addr1,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                             ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")

        # get current balance and nonce
        initial_state = aergo2.query_sc_state(token_pegged,
                                              ["_sv_Balances-" +
                                               sender,
                                               ])
        print("Token address in sidechain : ", token_pegged)
        if not initial_state.account.state_proof.inclusion:
            print("Pegged token doesnt exist in sidechain")
            aergo1.disconnect()
            aergo2.disconnect()
            return
        balance = json.loads(initial_state.var_proofs[0].value)
        print("Token balance on sidechain: ", balance)
        # balance on origin
        if aer:
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            origin_balance = aergo1.query_sc_state(token_origin,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        print("\n------ Burn tokens -----------")
        burn_height, success = burn(aergo2, receiver, addr2, token_pegged)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("------ Wait finalisation and get burn proof -----------")
        burn_proof, success = build_burn_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, burn_height,
                                               token_origin, t_anchor, t_final)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("\n------ Unlock tokens on origin blockchain -----------")
        if not unlock(aergo1, receiver, burn_proof, token_origin, addr1):
            aergo1.disconnect()
            aergo2.disconnect()
            return

        # remaining balance on sidechain
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   sender,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Balance on sidechain: ", balance)

        # new balance on origin
        if aer:
            aergo1.get_account()
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            origin_balance = aergo1.query_sc_state(token_origin,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                  e.details()))
    except KeyboardInterrupt:
        print("Shutting down operator")

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    # with open("./config.json", "r") as f:
        # config_data = json.load(f)
    # wallet = Wallet(config_data)
    # wallet.transfer_from_sidechain()
    run(aer=False)
