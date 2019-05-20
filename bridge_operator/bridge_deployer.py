from getpass import getpass
import json
import time

from typing import (
    Dict,
)

import aergo.herapy as herapy


COMMIT_TIME = 3


def run(
    config_data: Dict,
    payload_str: str,
    t_anchor_mainnet: int,
    t_anchor_sidechain: int,
    mainnet: str,
    sidechain: str,
    path: str = "./config.json",
    privkey_name: str = None,
    privkey_pwd: str = None
) -> None:
    if privkey_name is None:
        privkey_name = 'proposer'
    if privkey_pwd is None:
        privkey_pwd = getpass("Decrypt exported private key '{}'\nPassword: "
                              .format(privkey_name))
    payload = herapy.utils.decode_address(payload_str)
    print("------ DEPLOY BRIDGE BETWEEN CHAIN1 & CHAIN2 -----------")
    aergo1 = herapy.Aergo()
    aergo2 = herapy.Aergo()

    print("------ Connect AERGO -----------")
    aergo1.connect(config_data[mainnet]['ip'])
    aergo2.connect(config_data[sidechain]['ip'])

    status1 = aergo1.get_status()
    status2 = aergo2.get_status()
    height1 = status1.best_block_height
    height2 = status2.best_block_height
    lib1 = status1.consensus_info.status['LibNo']
    lib2 = status2.consensus_info.status['LibNo']
    # mainnet finalization time
    t_final_mainnet = height1 - lib1
    # sidechain finalization time
    t_final_sidechain = height2 - lib2

    print("------ Set Sender Account -----------")
    sender_priv_key1 = config_data['wallet'][privkey_name]['priv_key']
    sender_priv_key2 = config_data['wallet'][privkey_name]['priv_key']
    aergo1.import_account(sender_priv_key1, privkey_pwd)
    aergo2.import_account(sender_priv_key2, privkey_pwd)
    print("  > Sender Address: {}".format(aergo1.account.address))

    print("------ Deploy SC -----------")
    # get validators from config file
    validators = []
    for validator in config_data['validators']:
        validators.append(validator['addr'])
    print('validators : ', validators)
    tx1, result1 = aergo1.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor_mainnet,
                                          t_final_mainnet])
    tx2, result2 = aergo2.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor_sidechain,
                                          t_final_sidechain])
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
    if result1.status != herapy.TxResultStatus.CREATED:
        print("  > ERROR[{0}]:{1}: {2}"
              .format(result1.contract_address, result1.status,
                      result1.detail))
        aergo1.disconnect()
        aergo2.disconnect()
        return
    result2 = aergo2.get_tx_result(tx2.tx_hash)
    if result2.status != herapy.TxResultStatus.CREATED:
        print("  > ERROR[{0}]:{1}: {2}"
              .format(result2.contract_address, result2.status,
                      result2.detail))
        aergo1.disconnect()
        aergo2.disconnect()
        return

    sc_address1 = result1.contract_address
    sc_address2 = result2.contract_address
    sc_id1 = result1.detail[1:-1]
    sc_id2 = result2.detail[1:-1]

    print("  > SC Address CHAIN1: {}".format(sc_address1))
    print("  > SC Address CHAIN2: {}".format(sc_address2))

    print("------ Store bridge addresses in config.json  -----------")
    config_data[mainnet]['bridges'][sidechain] = {}
    config_data[sidechain]['bridges'][mainnet] = {}
    config_data[mainnet]['bridges'][sidechain]['addr'] = sc_address1
    config_data[sidechain]['bridges'][mainnet]['addr'] = sc_address2
    config_data[mainnet]['bridges'][sidechain]['id'] = sc_id1
    config_data[sidechain]['bridges'][mainnet]['id'] = sc_id2
    config_data[mainnet]['bridges'][sidechain]['t_anchor'] = t_anchor_mainnet
    config_data[mainnet]['bridges'][sidechain]['t_final'] = t_final_sidechain
    config_data[sidechain]['bridges'][mainnet]['t_anchor'] = t_anchor_sidechain
    config_data[sidechain]['bridges'][mainnet]['t_final'] = t_final_mainnet
    try:
        config_data[mainnet]['tokens']['aergo']
    except KeyError:
        pass
    else:
        # this is a new bridge, so remove any old pegged aergo with same name
        # bridge
        config_data[mainnet]['tokens']['aergo']['pegs'] = {}

    with open(path, "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./contracts/bridge_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    # NOTE t_final is the minimum time to get lib : only informative (not
    # actually used in code except for Eth bridge because Eth doesn't have LIB)
    t_anchor_mainnet = 25  # sidechain anchoring periord on mainnet
    t_anchor_sidechain = 10  # mainnet anchoring periord on sidechain
    run(config_data, payload_str,
        t_anchor_mainnet, t_anchor_sidechain,
        'mainnet', 'sidechain2')
