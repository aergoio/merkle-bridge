import argparse
from getpass import getpass
import json
import aergo.herapy as herapy


def deploy_bridge(
    config_file_path: str,
    payload_str: str,
    t_anchor1: int,
    t_final1: int,
    t_anchor2: int,
    t_final2: int,
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
    print("------ DEPLOY BRIDGE BETWEEN CHAIN1 & CHAIN2 -----------")
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
    tx1, result1 = aergo1.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor1,
                                          t_final1])
    tx2, result2 = aergo2.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor2,
                                          t_final2])
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
    sc_id1 = result1.detail[1:-1]
    sc_id2 = result2.detail[1:-1]

    print("  > SC Address CHAIN1: {}".format(sc_address1))
    print("  > SC Address CHAIN2: {}".format(sc_address2))

    print("------ Store bridge addresses in config.json  -----------")
    config_data['networks'][net1]['bridges'][net2] = {}
    config_data['networks'][net2]['bridges'][net1] = {}
    config_data['networks'][net1]['bridges'][net2]['addr'] = sc_address1
    config_data['networks'][net2]['bridges'][net1]['addr'] = sc_address2
    config_data['networks'][net1]['bridges'][net2]['id'] = sc_id1
    config_data['networks'][net2]['bridges'][net1]['id'] = sc_id2
    config_data['networks'][net1]['bridges'][net2]['t_anchor'] = t_anchor1
    config_data['networks'][net1]['bridges'][net2]['t_final'] = t_final1
    config_data['networks'][net2]['bridges'][net1]['t_anchor'] = t_anchor2
    config_data['networks'][net2]['bridges'][net1]['t_final'] = t_final2
    try:
        config_data['networks'][net1]['tokens']['aergo']
    except KeyError:
        pass
    else:
        # this is a new bridge, so remove any old pegged aergo with same name
        # bridge
        config_data['networks'][net1]['tokens']['aergo']['pegs'] = {}

    with open(config_file_path, "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)

    print("------ Disconnect AERGO -----------")
    aergo1.disconnect()
    aergo2.disconnect()


if __name__ == '__main__':
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
        '--t_anchor1', type=int, required=True,
        help='Anchoring periode (in Aergo blocks) of net2 on net1')
    parser.add_argument(
        '--t_final1', type=int, required=True,
        help='Finality of net2 (in Aergo blocks) root anchored on net1')
    parser.add_argument(
        '--t_anchor2', type=int, required=True,
        help='Anchoring periode (in Aergo blocks) of net1 on net2')
    parser.add_argument(
        '--t_final2', type=int, required=True,
        help='Finality of net1 (in Aergo blocks) root anchored on net2')
    parser.add_argument(
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)

    args = parser.parse_args()

    deploy_bridge(args.config_file_path, payload_str,
                  args.t_anchor1, args.t_final1, args.t_anchor2, args.t_final2,
                  args.net1, args.net2, privkey_name=args.privkey_name)
