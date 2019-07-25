from typing import (
    Tuple,
)

import aergo.herapy as herapy

from aergo_wallet.exceptions import (
    TxError,
    InvalidArgumentsError
)

from aergo_wallet.wallet_utils import (
    build_deposit_proof,
    is_aergo_address,
)


def burn(
    aergo_from: herapy.Aergo,
    bridge_from: str,
    receiver: str,
    value: int,
    token_pegged: str,
    fee_limit: int,
    fee_price: int,
    signed_transfer: Tuple[int, str, str, int] = None,
) -> Tuple[int, str]:
    """ Burn a minted token on a sidechain. """
    if not is_aergo_address(receiver):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(receiver)
        )
    args = (receiver, str(value), token_pegged)
    if signed_transfer is not None:
        args = args + signed_transfer
        tx, result = aergo_from.call_sc(bridge_from, "burn", args=args)
    else:
        tx, result = aergo_from.call_sc(bridge_from, "burn", args=args)

    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Burn asset Tx commit failed : {}".format(result))

    # Check burn success
    result = aergo_from.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Burn asset Tx execution failed : {}".format(result))
    # get precise burn height
    tx_detail = aergo_from.get_tx(tx.tx_hash)
    burn_height = tx_detail.block.height
    return burn_height, str(tx.tx_hash)


def build_burn_proof(
    aergo_from: herapy.Aergo,
    aergo_to: herapy.Aergo,
    receiver: str,
    bridge_from: str,
    bridge_to: str,
    burn_height: int,
    token_origin: str,
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the burn and build
    a burn proof for that root
    """
    return build_deposit_proof(
        aergo_from, aergo_to, receiver, bridge_from, bridge_to, burn_height,
        token_origin, "_sv_Burns-"
    )


def unlock(
    aergo_to: herapy.Aergo,
    receiver: str,
    burn_proof: herapy.obj.sc_state.SCState,
    token_origin: str,
    bridge_to: str,
    fee_limit: int,
    fee_price: int,
) -> str:
    """ Unlock the receiver's deposit balance on aergo_to. """
    if not is_aergo_address(receiver):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(receiver)
        )
    balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = burn_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call unlock on aergo_to with the burn proof from aergo_from
    tx, result = aergo_to.call_sc(bridge_to, "unlock",
                                  args=[receiver, balance,
                                        token_origin, ap])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Unlock asset Tx commit failed : {}".format(result))

    result = aergo_to.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Unlock asset Tx execution failed : {}".format(result))
    return str(tx.tx_hash)
