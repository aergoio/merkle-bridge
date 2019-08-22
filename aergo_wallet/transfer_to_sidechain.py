import json
from typing import (
    Tuple,
    Union,
)

import aergo.herapy as herapy

from aergo_wallet.exceptions import (
    TxError,
    InvalidArgumentsError,
)

from aergo_wallet.wallet_utils import (
    build_deposit_proof,
    is_aergo_address
)


def lock(
    aergo_from: herapy.Aergo,
    bridge_from: str,
    receiver: str,
    value: int,
    asset: str,
    fee_limit: int,
    fee_price: int,
) -> Tuple[int, str]:
    """ Lock can be called to lock aer or tokens.
        it supports delegated transfers when tx broadcaster is not
        the same as the token owner
    """
    if not is_aergo_address(receiver):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(receiver)
        )
    if not is_aergo_address(asset):
        raise InvalidArgumentsError(
            "asset {} must be an Aergo address".format(asset)
        )
    args = (bridge_from, {"_bignum": str(value)}, receiver)
    tx, result = aergo_from.call_sc(
        asset, "transfer", args=args, amount=0
    )
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Lock asset Tx commit failed : {}".format(result))

    # Check lock success
    result = aergo_from.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Lock asset Tx execution failed : {}".format(result))
    # get precise lock height
    tx_detail = aergo_from.get_tx(tx.tx_hash)
    lock_height = tx_detail.block.height
    return lock_height, str(tx.tx_hash)


def build_lock_proof(
    aergo_from: herapy.Aergo,
    aergo_to: herapy.Aergo,
    receiver: str,
    bridge_from: str,
    bridge_to: str,
    lock_height: int,
    token_origin: str,
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the lock and build
    a lock proof for that root
    """
    return build_deposit_proof(
        aergo_from, aergo_to, receiver, bridge_from, bridge_to, lock_height,
        token_origin, "_sv__locks-"
    )


def mint(
    aergo_to: herapy.Aergo,
    receiver: str,
    lock_proof: herapy.obj.sc_state.SCState,
    token_origin: str,
    bridge_to: str,
    fee_limit: int,
    fee_price: int
) -> Tuple[str, str]:
    """ Mint the receiver's deposit balance on aergo_to. """
    if not is_aergo_address(receiver):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(receiver)
        )
    auditPath = lock_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    ubig_balance = {'_bignum': str(balance)}
    # call mint on aergo_to with the lock proof from aergo_from
    tx, result = aergo_to.call_sc(bridge_to, "mint",
                                  args=[receiver, ubig_balance,
                                        token_origin, ap])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Mint asset Tx commit failed : {}".format(result))

    result = aergo_to.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Mint asset Tx execution failed : {}".format(result))
    token_pegged = json.loads(result.detail)[0]
    return token_pegged, str(tx.tx_hash)
