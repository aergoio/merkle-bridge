import grpc
import hashlib
import json
import sys
import time

import aergo.herapy as herapy
from exceptions import InvalidMerkleProofError, TxError

COMMIT_TIME = 3


def lock_aer(aergo_from, sender, receiver, bridge_from):
    # TODO pass in value
    # TODO check balance is enough in caller of this function
    # TODO print balance in caller
    print("aergo balance on origin before transfer",
          aergo_from.account.balance.aer)
    value = 1*10**18
    # TODO print transfering in caller
    print("Transfering", value/10**18, "aergo...")
    tx, result = aergo_from.call_sc(bridge_from, "lock",
                                    args=[receiver, str(value), "aergo"],
                                    amount=value)
    time.sleep(COMMIT_TIME)
    # Record lock height
    _, lock_height = aergo_from.get_blockchain_status()
    # Check lock success
    result = aergo_from.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address, result.status,
                              result.detail))
    print("Lock success : ", result.detail)
    return lock_height


def lock_token(aergo_from, sender, receiver, bridge_from, token_origin):
    # get current balance and nonce
    initial_state = aergo_from.query_sc_state(token_origin,
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
    print("Token balance on origin before transfer: ", balance/10**18)

    # make a signed transfer of 5000 tokens
    value = 1*10**18
    fee = 0
    deadline = 0
    contractID = str(contractID_p[1:-1], 'utf-8')
    msg = bytes(bridge_from + str(value) + str(nonce) + str(fee) +
                str(deadline) + contractID, 'utf-8')
    h = hashlib.sha256(msg).digest()
    sig = aergo_from.account.private_key.sign_msg(h).hex()

    # lock and check block height of lock tx
    print("Transfering", value/10**18, "tokens...")
    tx, result = aergo_from.call_sc(bridge_from, "lock",
                                    args=[receiver, str(value),
                                          token_origin, nonce, sig])
    time.sleep(COMMIT_TIME)
    # Record lock height
    _, lock_height = aergo_from.get_blockchain_status()
    # Check lock success
    result = aergo_from.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address, result.status,
                              result.detail))
    print("Lock success : ", result.detail)
    return lock_height


def build_lock_proof(aergo_from, aergo_to, receiver, bridge_from, bridge_to,
                     lock_height, token_origin, t_anchor, t_final):
    # check current merged height at destination
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    merged_height_to = int(height_proof_to.var_proofs[0].value)
    print("last merged height at destination :", merged_height_to)
    # wait t_final
    print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
    time.sleep(t_final)
    # check last merged height
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    last_merged_height_to = int(height_proof_to.var_proofs[0].value)
    # waite for anchor containing our transfer
    sys.stdout.write("waiting new anchor ")
    while last_merged_height_to < lock_height:
        sys.stdout.flush()
        sys.stdout.write(". ")
        time.sleep(t_anchor/4)
        height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
        last_merged_height_to = int(height_proof_to.var_proofs[0].value)
        # TODO do this with events when available
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
    account_ref = receiver + token_origin
    lock_proof = aergo_from.query_sc_state(bridge_from,
                                           ["_sv_Locks-" + account_ref],
                                           root=merge_block_from.blocks_root_hash,
                                           compressed=False)
    if not lock_proof.verify_proof(merge_block_from.blocks_root_hash):
        raise InvalidMerkleProofError("Unable to verify lock proof")
    return lock_proof


def mint(aergo_to, receiver, lock_proof, token_origin, bridge_to):
    balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = lock_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo_to with the lock proof from aergo_from
    tx, result = aergo_to.call_sc(bridge_to, "mint",
                                  args=[receiver, balance,
                                        token_origin, ap])
    time.sleep(COMMIT_TIME)
    result = aergo_to.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address,
                              result.status, result.detail))
    print("Mint success : ", result.detail)

    token_pegged = json.loads(result.detail)[0]
    return token_pegged


def test_script(aer=False):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    bridge_from = config_data['mainnet']['bridges']['sidechain2']
    bridge_to = config_data['sidechain2']['bridges']['mainnet']
    token_origin = config_data['mainnet']['tokens']['token1']['addr']
    if aer:
        token_origin = "aergo"
    try:
        aergo_from = herapy.Aergo()
        aergo_to = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo_from.connect(config_data['mainnet']['ip'])
        aergo_to.connect(config_data['sidechain2']['ip'])

        sender_private_key_from = config_data["wallet"]['priv_key']
        sender_priv_key_to = config_data["wallet"]['priv_key']
        sender_account = aergo_from.new_account(private_key=sender_private_key_from)
        aergo_to.new_account(private_key=sender_priv_key_to)
        aergo_from.get_account()
        aergo_to.get_account()

        sender = sender_account.address.__str__()
        receiver = sender
        print("  > Sender Address: ", sender)

        # Get bridge information
        bridge_info = aergo_from.query_sc_state(bridge_from,
                                                ["_sv_T_anchor",
                                                 "_sv_T_final",
                                                 ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")

        print("\n------ Lock tokens/aer -----------")
        if aer:
            lock_height = lock_aer(aergo_from, sender, receiver, bridge_from)
        else:
            lock_height = lock_token(aergo_from, sender, receiver, bridge_from,
                                     token_origin)

        print("------ Wait finalisation and get lock proof -----------")
        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      token_origin, t_anchor, t_final)

        print("\n------ Mint tokens on destination blockchain -----------")
        token_pegged = mint(aergo_to, receiver, lock_proof,
                            token_origin, bridge_to)

        # new balance on sidechain
        sidechain_balance = aergo_to.query_sc_state(token_pegged,
                                                    ["_sv_Balances-" +
                                                     receiver,
                                                     ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Pegged contract address on sidechain :", token_pegged)
        print("Balance on sidechain : ", balance)

        # remaining balance on origin
        if aer:
            aergo_from.get_account()
            print("Balance on origin: ", aergo_from.account.balance.aer)
        else:
            origin_balance = aergo_from.query_sc_state(token_origin,
                                                       ["_sv_Balances-" +
                                                        sender,
                                                        ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        # record mint address in file
        print("------ Store mint address in config.json -----------")
        config_data['mainnet']['tokens']['token1']['pegs']['sidechain2'] = token_pegged
        with open("./config.json", "w") as f:
            json.dump(config_data, f, indent=4, sort_keys=True)

    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'
              .format(e.code(), e.details()))
    except KeyboardInterrupt:
        print("Shutting down operator")

    print("------ Disconnect AERGO -----------")
    aergo_from.disconnect()
    aergo_to.disconnect()


if __name__ == '__main__':
    # with open("./config.json", "r") as f:
        # config_data = json.load(f)
    # wallet = Wallet(config_data)
    # wallet.transfer_to_sidechain()
    test_script(aer=False)
