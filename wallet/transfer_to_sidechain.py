import grpc
import hashlib
import json
import sys
import time

import aergo.herapy as herapy

COMMIT_TIME = 3


def lock_aer(aergo1, sender, receiver, addr1):
    print("Balance on origin", aergo1.account.balance.aer)
    value = 8*10**18
    print("Transfering", value, "aer...")
    tx, result = aergo1.call_sc(addr1, "lock",
                                args=[receiver, str(value), "aergo"],
                                amount=value)
    time.sleep(COMMIT_TIME)
    # Record lock height
    _, lock_height = aergo1.get_blockchain_status()
    # Check lock success
    result = aergo1.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        print("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
        return None, False
    print("Lock success : ", result.detail)
    return lock_height, True


def lock_token(aergo1, sender, receiver, addr1, token_origin):
    # get current balance and nonce
    initial_state = aergo1.query_sc_state(token_origin,
                                          ["_sv_Balances-" +
                                           sender,
                                           "_sv_Nonces-" +
                                           sender,
                                           "_sv_ContractID"
                                           ])
    balance_p, nonce_p, contractID_p = [item.value for item in initial_state.var_proofs]
    balance = int(json.loads(balance_p)["_bignum"])
    try:
        nonce = int(nonce_p)
    except ValueError:
        nonce = 0
    print("Token address : ", token_origin)
    print("Balance on origin: ", balance/10**18)

    # make a signed transfer of 5000 tokens
    value = 8*10**18
    fee = 0
    deadline = 0
    contractID = str(contractID_p[1:-1], 'utf-8')
    msg = bytes(addr1 + str(value) + str(nonce) + str(fee) +
                str(deadline) + contractID, 'utf-8')
    h = hashlib.sha256(msg).digest()
    sig = aergo1.account.private_key.sign_msg(h).hex()

    # lock and check block height of lock tx
    print("Transfering", value/10**18, "tokens...")
    tx, result = aergo1.call_sc(addr1, "lock",
                                args=[receiver, str(value),
                                      token_origin, nonce, sig])
    time.sleep(COMMIT_TIME)
    # Record lock height
    _, lock_height = aergo1.get_blockchain_status()
    # Check lock success
    result = aergo1.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        print("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
        return None, False
    print("Lock success : ", result.detail)
    return lock_height, True


def build_lock_proof(aergo1, aergo2, receiver, addr1, addr2, lock_height,
                     token_origin, t_anchor, t_final):
    # check current merged height at destination
    height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
    merged_height2 = int(height_proof_2.var_proofs[0].value)
    print("last merged height at destination :", merged_height2)
    # wait t_final
    print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
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
    account_ref = receiver + token_origin
    lock_proof = aergo1.query_sc_state(addr1, ["_sv_Locks-" + account_ref],
                                       root=merge_block1.blocks_root_hash,
                                       compressed=False)
    if not lock_proof.verify_proof(merge_block1.blocks_root_hash):
        print("Unable to verify lock proof")
        return None, False
    return lock_proof, True


def mint(aergo2, receiver, lock_proof, token_origin, addr2):
    balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = lock_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo2 with the lock proof from aergo1
    tx, result = aergo2.call_sc(addr2, "mint",
                                args=[receiver, balance,
                                      token_origin, ap])
    time.sleep(COMMIT_TIME)
    result = aergo2.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        print("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
        return None, False
    print("Mint success on sidechain : ", result.detail)

    token_pegged = json.loads(result.detail)[0]
    return token_pegged, True


def run(aer=False):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    with open("./wallet/token_address.txt", "r") as f:
        token_origin = f.readline()[:52]
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

        print("\n------ Lock tokens/aer -----------")
        if aer:
            lock_height, success = lock_aer(aergo1, sender, receiver, addr1)
        else:
            lock_height, success = lock_token(aergo1, sender, receiver, addr1,
                                              token_origin)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()

        print("------ Wait finalisation and get lock proof -----------")
        lock_proof, success = build_lock_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, lock_height,
                                               token_origin, t_anchor, t_final)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("\n------ Mint tokens on destination blockchain -----------")
        token_pegged, success = mint(aergo2, receiver, lock_proof,
                                     token_origin, addr2)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        # new balance on sidechain
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   receiver,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Pegged contract address on sidechain :", token_pegged)
        print("Balance on sidechain : ", balance)

        # remaining balance on origin
        if aer:
            aergo1.get_account()
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            origin_balance = aergo1.query_sc_state(token_origin,
                                                ["_sv_Balances-" +
                                                    sender,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        # record mint address in file
        with open("./wallet/token_pegged_address.txt", "w") as f:
            f.write(token_pegged)
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
    run(aer=False)
