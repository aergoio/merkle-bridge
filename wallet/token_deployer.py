import grpc
import json
import time

import aergo.herapy as herapy


COMMIT_TIME = 3


def run():
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./contracts/token_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    payload = herapy.utils.decode_address(payload_str)
    print("------ DEPLOY BRIDGE BETWEEN CHAIN1 & CHAIN2 -----------")
    try:
        aergo1 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data['aergo1']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data["wallet"]['priv_key']
        sender_account = aergo1.new_account(private_key=sender_priv_key1)
        aergo1.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

        print("------ Deploy Token-----------")
        tx1, result1 = aergo1.deploy_sc(amount=0,
                                        payload=payload,
                                        args=[500*10**6*10**18])
        if result1.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}".format(result1.status,
                                                 result1.detail))
            aergo1.disconnect()
            return
        print("    > result[{0}] : {1}".format(result1.tx_id,
                                               result1.status.name))

        time.sleep(COMMIT_TIME)

        print("------ Check deployment of SC -----------")
        result1 = aergo1.get_tx_result(tx1.tx_hash)
        if result1.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result1.contract_address, result1.status, result1.detail))
            aergo1.disconnect()
            return

        sc_address1 = result1.contract_address

        print("  > Token Address (ORIGIN): {}".format(sc_address1))

        print("------ Store addresse in config.json -----------")
        config_data['aergo1']['tokens']['token1']['addr'] = sc_address1
        with open("./config.json", "w") as f:
            json.dump(config_data, f, indent=4, sort_keys=True)

        print("------ Disconnect AERGO -----------")
        aergo1.disconnect()
    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                  e.details()))


if __name__ == '__main__':
    run()
