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
        sender_priv_key1 = config_data['aergo1']['priv_key']
        sender_priv_key2 = config_data['aergo2']['priv_key']
        sender_account = aergo1.new_account(password="test",
                                            private_key=sender_priv_key1)
        aergo2.new_account(password="test",
                           private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: ", sender_account.address.__str__())

        t_anchor_p = aergo1.query_sc_state(addr1, "T_anchor")
        t_final_p = aergo1.query_sc_state(addr1, "T_final")
        t_anchor = int(t_anchor_p.var_proof.var_proof.value)
        t_final = int(t_final_p.var_proof.var_proof.value)

        print(" * anchoring periode : ", t_anchor, "s\n",
            "* chain finality periode : ", t_final, "s\n")

        print("------ Lock tokens -----------")
        # get current balance and nonce
        balance_p = aergo1.query_sc_state(token, "Balances",
                                          sender_account.address.__str__())
        nonce_p = aergo1.query_sc_state(token, "Nonces",
                                          sender_account.address.__str__())
        balance = int(balance_p.var_proof.var_proof.value)
        try:
            nonce = int(nonce_p.var_proof.var_proof.value)
        except ValueError:
            nonce = 0
        print("Token address : ", token)
        print("Token balance in origin contract : ", balance, "    nonce : ", nonce)

        # record current lock balance
        account_ref = sender_account.address.__str__() + token
        lock_p = aergo1.query_sc_state(addr1, "Locks", account_ref)
        try:
            lock_before = int(lock_p.var_proof.var_proof.value)
        except ValueError:
            lock_before = 0
        print("Current locked balance : ", lock_before)

        # make a signed transfer of 5 tokens
        to = sender_account.address.__str__()
        value = 5
        fee = 0
        deadline = 0
        # Get the contract's id
        contractID_p = aergo1.query_sc_state(token, "ContractID")
        contractID = str(contractID_p.var_proof.var_proof.value[1:-1], 'utf-8')
        msg = bytes(addr1 + str(value) + str(nonce) + str(fee) +
                    str(deadline) + contractID, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = aergo1.account.private_key.sign_msg(h).hex()

        # lock and check block height of lock tx
        tx, result = aergo1.call_sc(addr1, "lock",
                                    args=[to, value, token, nonce, sig])
        time.sleep(3)
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        lock_p = aergo1.query_sc_state(addr1, "Locks", account_ref)
        lock_after = int(lock_p.var_proof.var_proof.value)
        print("New locked balance : ", lock_after)

        print("------ Wait finalisation to create lock proof -----------")
        # check current merged height at destination
        # wait t_final
        # check last merged height
        # while last merged height < lock tx height
        ##### sleep(t_anchor / 4)
        # get inclusion proof of last merged block
        # check locked amount is recored in balance
        # TODO this requires contract deployment from with contract suport by
        # lua
        # call mint with the proof
        # check nuwly minted balance

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
