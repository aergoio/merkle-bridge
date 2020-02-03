import argparse
from getpass import getpass
import json
import aergo.herapy as herapy


def deploy_bridge(
    config_file_path: str,
    payload_str: str,
    net1: str,
    net2: str,
    privkey_name: str = None,
    privkey_pwd: str = None
) -> None:
    payload = herapy.utils.decode_address(payload_str)
    with open(config_file_path, "r") as f:
        config_data = json.load(f)
    t_anchor1 = config_data['networks'][net1]['bridges'][net2]['t_anchor']
    t_final1 = config_data['networks'][net1]['bridges'][net2]['t_final']
    t_anchor2 = config_data['networks'][net2]['bridges'][net1]['t_anchor']
    t_final2 = config_data['networks'][net2]['bridges'][net1]['t_final']
    print("------ DEPLOY BRIDGE BETWEEN {} & {} -----------".format(net1,
                                                                    net2))
    aergo1 = herapy.Aergo()
    aergo2 = herapy.Aergo()

    print("------ Connect AERGO -----------")
    aergo1.connect(config_data['networks'][net1]['ip'])
    aergo2.connect(config_data['networks'][net2]['ip'])

    print("------ Set Sender Account -----------")
    if privkey_name is None:
        privkey_name = 'proposer'
    if privkey_pwd is None:
        privkey_pwd = getpass("Decrypt Aergo keystore: '{}'\nPassword: "
                              .format(privkey_name))
    keystore_path1 = config_data['wallet'][privkey_name]['keystore']
    keystore_path2 = config_data['wallet'][privkey_name]['keystore']
    with open(keystore_path1, "r") as f:
        keystore1 = f.read()
    with open(keystore_path2, "r") as f:
        keystore2 = f.read()
    aergo1.import_account_from_keystore(keystore1, privkey_pwd)
    aergo2.import_account_from_keystore(keystore2, privkey_pwd)
    print("  > Sender Address: {}".format(aergo1.account.address))

    print("------ Deploy SC -----------")
    tx1, result1 = aergo1.deploy_sc(
        amount=0, payload=payload, args=[t_anchor1, t_final1])
    tx2, result2 = aergo2.deploy_sc(
        amount=0, payload=payload, args=[t_anchor2, t_final2])
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

    print("------ Check deployment of SC -----------")
    result1 = aergo1.wait_tx_result(tx1.tx_hash)
    if result1.status != herapy.TxResultStatus.CREATED:
        print("  > ERROR[{0}]:{1}: {2}"
              .format(result1.contract_address, result1.status,
                      result1.detail))
        aergo1.disconnect()
        aergo2.disconnect()
        return
    result2 = aergo2.wait_tx_result(tx2.tx_hash)
    if result2.status != herapy.TxResultStatus.CREATED:
        print("  > ERROR[{0}]:{1}: {2}"
              .format(result2.contract_address, result2.status,
                      result2.detail))
        aergo1.disconnect()
        aergo2.disconnect()
        return

    sc_address1 = result1.contract_address
    sc_address2 = result2.contract_address

    print("  > Bridge Address {}: {}".format(net1, sc_address1))
    print("  > Bridge Address {}: {}".format(net2, sc_address2))

    print("------ Store bridge addresses in config.json  -----------")
    config_data['networks'][net1]['bridges'][net2]['addr'] = sc_address1
    config_data['networks'][net2]['bridges'][net1]['addr'] = sc_address2

    with open(config_file_path, "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    print("\n\nDEPLOY BRIDGE")
    with open("contracts/bridge_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    parser = argparse.ArgumentParser(
        description='Deploy bridge contracts between 2 Aergo networks.')
    # Add arguments
    parser.add_argument(
        '-c', '--config_file_path', type=str, help='Path to config.json',
        required=True)
    parser.add_argument(
        '--net1', type=str, required=True,
        help='Name of Aergo network in config file')
    parser.add_argument(
        '--net2', type=str, required=True,
        help='Name of Aergo network in config file')
    parser.add_argument(
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)
    parser.add_argument(
        '--local_test', dest='local_test', action='store_true',
        help='Start all validators locally for convenient testing')

    parser.set_defaults(local_test=False)
    args = parser.parse_args()

    if args.local_test:
        deploy_bridge(args.config_file_path, payload_str,
                      args.net1, args.net2,
                      privkey_name=args.privkey_name,
                      privkey_pwd='1234')
    else:
        deploy_bridge(args.config_file_path, payload_str,
                      args.net1, args.net2,
                      privkey_name=args.privkey_name)
