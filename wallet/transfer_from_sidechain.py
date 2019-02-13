import grpc
import json
import sys
import time

import aergo.herapy as herapy
from wallet.exceptions import UnknownContractError, TxError, InvalidMerkleProofError

COMMIT_TIME = 3


def burn(aergo_from, sender, receiver, value, token_pegged, bridge_from):
    # get current balance and nonce
    initial_state = aergo_from.query_sc_state(token_pegged,
                                              ["_sv_Balances-" +
                                               sender,
                                               ])
    if not initial_state.account.state_proof.inclusion:
        raise UnknownContractError("Pegged token doesnt exist in sidechain")
    # TODO handle balance with no funds, test
    balance = json.loads(initial_state.var_proofs[0].value)['_bignum']
    print("Token balance on origin before transfer: ", int(balance)/10**18)

    # lock and check block height of lock tx
    print("Transfering", value/10**18, "tokens...")
    tx, result = aergo_from.call_sc(bridge_from, "burn",
                                    args=[receiver, str(value), token_pegged])
    time.sleep(COMMIT_TIME)
    # Record burn height
    _, burn_height = aergo_from.get_blockchain_status()
    # Check burn success
    result = aergo_from.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address, result.status,
                              result.detail))
    print("Burn success : ", result.detail)
    return burn_height


def build_burn_proof(aergo_to, aergo_from, receiver, bridge_to, bridge_from,
                     burn_height, token_origin, t_anchor, t_final):
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
    while last_merged_height_to < burn_height:
        sys.stdout.flush()
        sys.stdout.write(". ")
        time.sleep(t_anchor/4)
        height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
        last_merged_height_to = int(height_proof_to.var_proofs[0].value)
        # TODO do this with events when available
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
    account_ref = receiver + token_origin
    burn_proof = aergo_from.query_sc_state(bridge_from,
                                           ["_sv_Burns-" + account_ref],
                                           root=merge_block_from.blocks_root_hash,
                                           compressed=False)
    if not burn_proof.verify_proof(merge_block_from.blocks_root_hash):
        raise InvalidMerkleProofError("Unable to verify burn proof")
    return burn_proof


def unlock(aergo_to, receiver, burn_proof, token_origin, bridge_to):
    balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = burn_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo_from with the lock proof from aergo_to
    tx, result = aergo_to.call_sc(bridge_to, "unlock",
                                  args=[receiver, balance,
                                        token_origin, ap])
    time.sleep(COMMIT_TIME)
    result = aergo_to.get_tx_result(tx.tx_hash)
    if result.status != herapy.SmartcontractStatus.SUCCESS:
        raise TxError("  > ERROR[{0}]:{1}: {2}"
                      .format(result.contract_address, result.status,
                              result.detail))

    print("Unlock success on origin : ", result.detail)


def test_script(aer=False):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    bridge_to = config_data['mainnet']['bridges']['sidechain2']
    bridge_from = config_data['sidechain2']['bridges']['mainnet']
    token_pegged = config_data['mainnet']['tokens']['token1']['pegs']['sidechain2']
    token_origin = config_data['mainnet']['tokens']['token1']['addr']
    if aer:
        token_origin = "aergo"
    try:
        aergo_to = herapy.Aergo()
        aergo_from = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo_to.connect(config_data['mainnet']['ip'])
        aergo_from.connect(config_data['sidechain2']['ip'])

        sender_priv_key_to = config_data["wallet"]['priv_key']
        sender_priv_key_from = config_data["wallet"]['priv_key']
        sender_account = aergo_to.new_account(private_key=sender_priv_key_to)
        aergo_from.new_account(private_key=sender_priv_key_from)
        aergo_to.get_account()
        aergo_from.get_account()

        sender = sender_account.address.__str__()
        receiver = sender
        print("  > Sender Address: ", sender)

        # Get bridge information
        bridge_info = aergo_to.query_sc_state(bridge_to,
                                              ["_sv_T_anchor",
                                               "_sv_T_final",
                                               ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")

        # get current balance and nonce
        initial_state = aergo_from.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   sender,
                                                   ])
        print("Token address in sidechain : ", token_pegged)
        if not initial_state.account.state_proof.inclusion:
            print("Pegged token doesnt exist in sidechain")
            aergo_to.disconnect()
            aergo_from.disconnect()
            return
        balance = json.loads(initial_state.var_proofs[0].value)
        print("Token balance on sidechain: ", balance)
        # balance on origin
        if aer:
            print("Balance on origin: ", aergo_to.account.balance.aer)
        else:
            origin_balance = aergo_to.query_sc_state(token_origin,
                                                     ["_sv_Balances-" +
                                                      receiver,
                                                      ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        print("\n------ Burn tokens -----------")
        burn_height = burn(aergo_from, sender, receiver, 1*10**18,
                           token_pegged, bridge_from)

        print("------ Wait finalisation and get burn proof -----------")
        burn_proof = build_burn_proof(aergo_to, aergo_from, receiver,
                                      bridge_to, bridge_from, burn_height,
                                      token_origin, t_anchor, t_final)

        print("\n------ Unlock tokens on origin blockchain -----------")
        unlock(aergo_to, receiver, burn_proof, token_origin, bridge_to)

        # remaining balance on sidechain
        sidechain_balance = aergo_from.query_sc_state(token_pegged,
                                                      ["_sv_Balances-" +
                                                       sender,
                                                       ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Balance on sidechain: ", balance)

        # new balance on origin
        if aer:
            aergo_to.get_account()
            print("Balance on origin: ", aergo_to.account.balance.aer)
        else:
            origin_balance = aergo_to.query_sc_state(token_origin,
                                                     ["_sv_Balances-" +
                                                      receiver,
                                                      ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'
              .format(e.code(), e.details()))
    except KeyboardInterrupt:
        print("Shutting down operator")

    print("------ Disconnect AERGO -----------")
    aergo_to.disconnect()
    aergo_from.disconnect()


if __name__ == '__main__':
    # with open("./config.json", "r") as f:
        # config_data = json.load(f)
    # wallet = Wallet(config_data)
    # wallet.transfer_from_sidechain()
    test_script(aer=False)
