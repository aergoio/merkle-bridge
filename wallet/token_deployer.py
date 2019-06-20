from getpass import getpass
import json
import time

import aergo.herapy as herapy

from wallet.exceptions import (
    TxError,
)


COMMIT_TIME = 3


def deploy_token(
    payload_str: str,
    aergo: herapy.Aergo,
    receiver: str,
    total_supply: int,
    fee_limit: int,
    fee_price: int
) -> str:
    """ Deploy a token contract payload and give the
    total supply to the deployer
    """
    payload = herapy.utils.decode_address(payload_str)
    print("------ Deploy Token-----------")
    tx, result = aergo.deploy_sc(amount=0,
                                 payload=payload,
                                 args=[str(total_supply), receiver])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Token deployment Tx commit failed : {}".format(result))
    print("    > result[{0}] : {1}"
          .format(result.tx_id, result.status.name))

    time.sleep(COMMIT_TIME)

    print("------ Check deployment of SC -----------")
    result = aergo.get_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.CREATED:
        raise TxError("Token deployment Tx execution failed : {}"
                      .format(result))

    sc_address = result.contract_address

    print("  > Token Address : {}".format(sc_address))

    return sc_address


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    with open("./contracts/token_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]

    aergo = herapy.Aergo()

    print("------ Connect AERGO -----------")
    aergo.connect(config_data['networks']['mainnet']['ip'])

    print("------ Set Sender Account -----------")
    privkey_name = 'default'
    sender_priv_key = config_data["wallet"][privkey_name]['priv_key']
    privkey_pwd = getpass("Decrypt exported private key '{}'\nPassword: "
                          .format(privkey_name))
    aergo.import_account(sender_priv_key, privkey_pwd)
    receiver = aergo.account.address.__str__()
    print("  > Sender Address: {}".format(receiver))

    total_supply = 500*10**6*10**18

    sc_address = deploy_token(payload_str, aergo,
                              receiver, total_supply, 0, 0)

    print("------ Disconnect AERGO -----------")
    aergo.disconnect()

    print("------ Store addresse in config.json -----------")
    config_data['networks']['mainnet']['tokens']['token1'] = {}
    config_data['networks']['mainnet']['tokens']['token1']['addr'] = sc_address
    config_data['networks']['mainnet']['tokens']['token1']['pegs'] = {}
    with open("./config.json", "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)
