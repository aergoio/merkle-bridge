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
    print("------ DEPLOY TOKEN ON MAINNET -----------")
    try:
        aergo = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo.connect(config_data['mainnet']['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key = config_data["wallet"]['priv_key']
        sender_account = aergo.new_account(private_key=sender_priv_key)
        aergo.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

        print("------ Deploy Token-----------")
        tx, result = aergo.deploy_sc(amount=0,
                                     payload=payload,
                                     args=[500*10**6*10**18])
        if result.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}"
                  .format(result.status, result.detail))
            aergo.disconnect()
            return
        print("    > result[{0}] : {1}"
              .format(result.tx_id, result.status.name))

        time.sleep(COMMIT_TIME)

        print("------ Check deployment of SC -----------")
        result = aergo.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}"
                  .format(result.contract_address, result.status,
                          result.detail))
            aergo.disconnect()
            return

        sc_address = result.contract_address

        print("  > Token Address (MAINNET): {}".format(sc_address))

        print("------ Store addresse in config.json -----------")
        config_data['mainnet']['tokens']['token1']['addr'] = sc_address
        with open("./config.json", "w") as f:
            json.dump(config_data, f, indent=4, sort_keys=True)

        print("------ Disconnect AERGO -----------")
        aergo.disconnect()
    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'
              .format(e.code(), e.details()))


if __name__ == '__main__':
    run()
