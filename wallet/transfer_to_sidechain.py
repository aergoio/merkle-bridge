import grpc
import hashlib
import json
import sys
import time

import aergo.herapy as herapy
from exceptions import *

COMMIT_TIME = 3


def lock_aer(aergo1, sender, receiver, addr1):
    # TODO pass in value
    # TODO check balance is enough in caller of this function
    # TODO print balance in caller
    print("aergo balance on origin before transfer", aergo1.account.balance.aer)
    value = 1*10**18
    # TODO print transfering in caller
    print("Transfering", value/10**18, "aergo...")
    tx, result = aergo1.call_sc(addr1, "lock",
                                args=[receiver, str(value), "aergo"],
                                amount=value)
    time.sleep(COMMIT_TIME)
    # Record lock height
    _, lock_height = aergo1.get_blockchain_status()
    # Check lock success
    result = aergo1.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
    print("Lock success : ", result.detail)
    return lock_height


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
    print("Token balance on origin before transfer: ", balance/10**18)

    # make a signed transfer of 5000 tokens
    value = 1*10**18
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
        raise TxError("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
    print("Lock success : ", result.detail)
    return lock_height


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
        raise InvalidMerkleProofError("Unable to verify lock proof")
    return lock_proof


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
        raise TxError("  > ERROR[{0}]:{1}: {2}".format(
            result.contract_address, result.status, result.detail))
    print("Mint success : ", result.detail)

    token_pegged = json.loads(result.detail)[0]
    return token_pegged


def test_script(aer=False):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    addr1 = config_data['mainnet']['bridges']['sidechain2']
    addr2 = config_data['sidechain2']['bridges']['mainnet']
    token_origin = config_data['mainnet']['tokens']['token1']['addr']
    if aer:
        token_origin = "aergo"
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['mainnet']['ip'])
        aergo2.connect(config_data['sidechain2']['ip'])

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
            lock_height = lock_aer(aergo1, sender, receiver, addr1)
        else:
            lock_height = lock_token(aergo1, sender, receiver, addr1,
                                            token_origin)

        print("------ Wait finalisation and get lock proof -----------")
        lock_proof = build_lock_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, lock_height,
                                               token_origin, t_anchor, t_final)

        print("\n------ Mint tokens on destination blockchain -----------")
        token_pegged = mint(aergo2, receiver, lock_proof,
                                     token_origin, addr2)

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
        print("------ Store mint address in config.json -----------")
        config_data['mainnet']['tokens']['token1']['pegs']['sidechain2'] = token_pegged
        with open("./config.json", "w") as f:
            json.dump(config_data, f, indent=4, sort_keys=True)

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
    # wallet.transfer_to_sidechain()
    test_script(aer=False)
