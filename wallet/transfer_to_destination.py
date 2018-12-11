import grpc

import aergo.herapy as herapy


def run():
    with open("./bridge_operator/bridge_addresses.txt", "r") as f:
        addr1 = f.readline()[:52]
        addr2 = f.readline()[:52]
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect('localhost:7845')
        aergo2.connect('localhost:8845')

        print("------ Set Sender Account -----------")
        sender_priv_key = "6hbRWgddqcg2ZHE5NipM1xgwBDAKqLnCKhGvADWrWE18xAbX8sW"
        sender_account = aergo1.new_account(password="test",
                                            private_key=sender_priv_key)
        aergo2.new_account(password="test",
                           private_key=sender_priv_key)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

        t_anchor_p = aergo1.query_sc_state(addr1, "T_anchor")
        t_final_p = aergo1.query_sc_state(addr1, "T_final")
        t_anchor = int(t_anchor_p.var_proof.var_proof.value)
        t_final = int(t_final_p.var_proof.var_proof.value)

        print(" * anchoring periode : ", t_anchor, "s\n",
            "* chain finality periode : ", t_final, "s\n")

        # record current lock balance
        # sign token nonce
        # lock and check block height of lock tx
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
