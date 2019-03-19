import hashlib
import json
import time
from typing import (
    Tuple,
    Optional,
)

import aergo.herapy as herapy

from wallet.exceptions import (
    InvalidArgumentsError,
    InsufficientBalanceError,
    TxError,
)

COMMIT_TIME = 3


# Wallet utils are made to be used with a custom herapy provider


def get_balance(
    account_addr: str,
    asset_addr: str,
    aergo: herapy.Aergo,
) -> int:
    """ Get an account or the default wallet balance of Aer
    or any token on a given network.
    """
    balance = 0
    if asset_addr == "aergo":
        # query aergo bits on network_name
        ret_account = aergo.get_account(address=account_addr)
        balance = ret_account.balance
    else:
        balance_q = aergo.query_sc_state(asset_addr,
                                         ["_sv_Balances-" +
                                          account_addr]
                                         )
        if balance_q.var_proofs[0].inclusion:
            balance = json.loads(balance_q.var_proofs[0].value)['_bignum']
    return int(balance)


def transfer(
    value: int,
    to: str,
    asset_addr: str,
    aergo: herapy.Aergo,
    sender: str,
    signed_transfer: Tuple[int, str] = None,
    delegate_data: Tuple[str, int] = None
) -> bool:
    """
    TODO https://github.com/Dexaran/ERC223-token-standard/blob/
    16d350ec85d5b14b9dc857468c8e0eb4a10572d3/ERC223_Token.sol#L107
    """
    # TODO support signed transfer and test sending to a contract that
    # supports token_payable and to pubkey account
    # TODO verify signature before sending tx in case of signed transfer
    # -> by broadcaster
    aergo.get_account()  # get the latest nonce for making tx

    balance = get_balance(sender, asset_addr, aergo)
    if balance < value:
        raise InsufficientBalanceError("not enough balance")

    if asset_addr == "aergo":
        # transfer aer on network_name
        if signed_transfer is not None:
            raise InvalidArgumentsError("cannot make aer signed transfer")

        tx, result = aergo.send_payload(to_address=to,
                                        amount=value, payload=None)
    else:
        # transfer token (issued or pegged) on network_name
        if signed_transfer is not None and delegate_data is not None:
            fee, deadline = delegate_data
            nonce, sig = signed_transfer
            tx, result = aergo.call_sc(asset_addr, "signed_transfer",
                                       args=[sender, to, str(value),
                                             nonce, sig, fee, deadline],
                                       amount=0)
        else:
            tx, result = aergo.call_sc(asset_addr, "transfer",
                                       args=[to, str(value)],
                                       amount=0)

    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Transfer asset Tx commit failed : {}"
                      .format(result))

    time.sleep(COMMIT_TIME)
    # Check lock success
    result = aergo.get_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Transfer asset Tx execution failed : {}"
                      .format(result))

    print("Transfer success")
    return True


def get_signed_transfer(
    value: int,
    to: str,
    asset_addr: str,
    aergo: herapy.Aergo,
    fee: int = 0,
    deadline: int = 0,
) -> Tuple[Tuple[int, str], Optional[Tuple[str, int]], int]:
    """Sign a standard token transfer to be broadcasted by a 3rd party"""
    # get current balance and nonce
    sender = str(aergo.account.address)
    initial_state = aergo.query_sc_state(asset_addr,
                                         ["_sv_Balances-" + sender,
                                          "_sv_Nonces-" + sender,
                                          "_sv_ContractID"
                                          ])
    balance_p, nonce_p, contractID_p = \
        [item.value for item in initial_state.var_proofs]
    balance = int(json.loads(balance_p)["_bignum"])

    try:
        nonce = int(nonce_p)
    except ValueError:
        nonce = 0

    contractID = str(contractID_p[1:-1], 'utf-8')
    msg = bytes(to + str(value) + str(nonce) + str(fee) +
                str(deadline) + contractID, 'utf-8')
    h = hashlib.sha256(msg).digest()
    sig = aergo.account.private_key.sign_msg(h).hex()

    signed_transfer = (nonce, sig)
    if fee == 0 and deadline == 0:
        delegate_data = None
    else:
        delegate_data = (str(fee), deadline)
    return signed_transfer, delegate_data, balance
