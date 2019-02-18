import json
import grpc
import time

import aergo.herapy as herapy


COMMIT_TIME = 3


def run(mainnet='mainnet', sidechain='sidechain2'):
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./contracts/bridge_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    payload = herapy.utils.decode_address(payload_str)
    print("------ DEPLOY BRIDGE BETWEEN CHAIN1 & CHAIN2 -----------")
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect(config_data[mainnet]['ip'])
        aergo2.connect(config_data[sidechain]['ip'])

        print("------ Set Sender Account -----------")
        sender_priv_key1 = config_data["proposer"]['priv_key']
        sender_priv_key2 = config_data["proposer"]['priv_key']
        sender_account = aergo1.new_account(private_key=sender_priv_key1)
        sender_address = sender_account.address.__str__()
        aergo2.new_account(private_key=sender_priv_key2)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))

        print("------ Deploy SC -----------")
        t_anchor = config_data['t_anchor']
        t_final = config_data['t_final']
        # get validators from config file
        validators = []
        for validator in config_data['validators']:
            validators.append(validator['addr'])
        print('validators : ', validators)
        tx1, result1 = aergo1.deploy_sc(amount=0,
                                        payload=payload,
                                        args=[validators,
                                              t_anchor,
                                              t_final])
        tx2, result2 = aergo2.deploy_sc(amount=0,
                                        payload=payload,
                                        args=[validators,
                                              t_anchor,
                                              t_final])
        if result1.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}"
                  .format(result1.status, result1.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("    > result[{0}] : {1}"
              .format(result1.tx_id, result1.status.name))
        if result2.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}"
                  .format(result2.status, result2.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        print("    > result[{0}] : {1}"
              .format(result2.tx_id, result2.status.name))

        time.sleep(COMMIT_TIME)

        print("------ Check deployment of SC -----------")
        result1 = aergo1.get_tx_result(tx1.tx_hash)
        if result1.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}"
                  .format(result1.contract_address, result1.status,
                          result1.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return
        result2 = aergo2.get_tx_result(tx2.tx_hash)
        if result2.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}"
                  .format(result2.contract_address, result2.status,
                          result2.detail))
            aergo1.disconnect()
            aergo2.disconnect()
            return

        sc_address1 = result1.contract_address
        sc_address2 = result2.contract_address

        print("  > SC Address CHAIN1: {}".format(sc_address1))
        print("  > SC Address CHAIN2: {}".format(sc_address2))

        print("------ Store bridge addresses in config.json  -----------")
        config_data[mainnet]['bridges'][sidechain] = sc_address1
        config_data[sidechain]['bridges'][mainnet] = sc_address2
        with open("./config.json", "w") as f:
            json.dump(config_data, f, indent=4, sort_keys=True)

        print("------ Disconnect AERGO -----------")
        aergo1.disconnect()
        aergo2.disconnect()
    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'
              .format(e.code(), e.details()))


if __name__ == '__main__':
    run(mainnet='mainnet', sidechain='sidechain2')
