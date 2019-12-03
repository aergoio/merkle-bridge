import argparse
from getpass import getpass
import hashlib
import json
import aergo.herapy as herapy
from aergo.herapy.utils.encoding import (
    decode_address,
)


def deploy_oracle(
    config_file_path: str,
    payload_str: str,
    net1: str,
    net2: str,
    privkey_name: str = None,
    privkey_pwd: str = None
) -> None:
    if privkey_name is None:
        privkey_name = 'proposer'
    if privkey_pwd is None:
        privkey_pwd = getpass("Decrypt exported private key '{}'\nPassword: "
                              .format(privkey_name))
    payload = herapy.utils.decode_address(payload_str)
    with open(config_file_path, "r") as f:
        config_data = json.load(f)
    print("------ DEPLOY ORACLE BETWEEN {} & {} -----------".format(
        net1, net2))
    aergo1 = herapy.Aergo()
    aergo2 = herapy.Aergo()

    print("------ Connect AERGO -----------")
    aergo1.connect(config_data['networks'][net1]['ip'])
    aergo2.connect(config_data['networks'][net2]['ip'])

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
    bridge1 = config_data['networks'][net1]['bridges'][net2]['addr']
    bridge2 = config_data['networks'][net2]['bridges'][net1]['addr']
    bridge_trie_key1 = \
        "0x" + hashlib.sha256(decode_address(bridge1)).digest().hex()
    bridge_trie_key2 = \
        "0x" + hashlib.sha256(decode_address(bridge2)).digest().hex()
    t_anchor1 = config_data['networks'][net1]['bridges'][net2]['t_anchor']
    t_final1 = config_data['networks'][net1]['bridges'][net2]['t_final']
    t_anchor2 = config_data['networks'][net2]['bridges'][net1]['t_anchor']
    t_final2 = config_data['networks'][net2]['bridges'][net1]['t_final']
    # get already deployed bridge addresses from config,json
    tx1, result1 = aergo1.deploy_sc(
        amount=0, payload=payload,
        args=[validators, bridge1, bridge_trie_key2, t_anchor1, t_final1]
    )
    tx2, result2 = aergo2.deploy_sc(
        amount=0, payload=payload,
        args=[validators, bridge2, bridge_trie_key1, t_anchor2, t_final2]
    )
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

    oracle1 = result1.contract_address
    oracle2 = result2.contract_address

    print("  > Oracle Address {}: {}".format(net1, oracle1))
    print("  > Oracle Address {}: {}".format(net2, oracle2))

    print("------ Store bridge addresses in config.json  -----------")
    config_data['networks'][net1]['bridges'][net2]['oracle'] = oracle1
    config_data['networks'][net2]['bridges'][net1]['oracle'] = oracle2

    with open(config_file_path, "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)

    print("------ Transfer bridge control to oracles -----------")
    tx1, result1 = aergo1.call_sc(
        bridge1, "oracleUpdate", args=[oracle1], amount=0
    )
    tx2, result2 = aergo2.call_sc(
        bridge2, "oracleUpdate", args=[oracle2], amount=0
    )
    if result1.status != herapy.CommitStatus.TX_OK:
        print("oracleUpdate Tx commit failed : {}".format(result1))
        aergo1.disconnect()
        aergo2.disconnect()
        return
    if result2.status != herapy.CommitStatus.TX_OK:
        print("oracleUpdate Tx commit failed : {}".format(result2))
        aergo1.disconnect()
        aergo2.disconnect()
        return

    # Check oracle transfer success
    result1 = aergo1.wait_tx_result(tx1.tx_hash)
    if result1.status != herapy.TxResultStatus.SUCCESS:
        print("oracleUpdate Tx execution failed : {}".format(result1))
        aergo1.disconnect()
        aergo2.disconnect()
        return
    result2 = aergo2.wait_tx_result(tx2.tx_hash)
    if result2.status != herapy.TxResultStatus.SUCCESS:
        print("oracleUpdate Tx execution failed : {}".format(result2))
        aergo1.disconnect()
        aergo2.disconnect()
        return

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
    print("\n\nDEPLOY ORACLE")
    with open("contracts/oracle_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    parser = argparse.ArgumentParser(
        description='Deploy oracle contracts to controle the bridge between '
                    '2 Aergo networks.')
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
        deploy_oracle(args.config_file_path, payload_str,
                      args.net1, args.net2,
                      privkey_name=args.privkey_name,
                      privkey_pwd='1234')
    else:
        deploy_oracle(args.config_file_path, payload_str,
                      args.net1, args.net2,
                      privkey_name=args.privkey_name)
