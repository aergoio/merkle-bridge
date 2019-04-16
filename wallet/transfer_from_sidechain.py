import sys
import time

from typing import (
    Tuple,
)

import aergo.herapy as herapy

from wallet.exceptions import (
    TxError,
    InvalidMerkleProofError,
)

COMMIT_TIME = 3


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
    args = (receiver, str(value), token_pegged)
    if signed_transfer is not None:
        args = args + signed_transfer
        tx, result = aergo_from.call_sc(bridge_from, "burn", args=args)
    else:
        tx, result = aergo_from.call_sc(bridge_from, "burn", args=args)

    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Burn asset Tx commit failed : {}".format(result))
    time.sleep(COMMIT_TIME)

    # Check burn success
    result = aergo_from.get_tx_result(tx.tx_hash)
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
    t_anchor: int
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the burn and build
    a burn proof for that root
    """
    # check last merged height
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    last_merged_height_to = int(height_proof_to.var_proofs[0].value)
    # waite for anchor containing our transfer
    if last_merged_height_to < burn_height:
        sys.stdout.write("waiting new anchor ")
    while last_merged_height_to < burn_height:
        sys.stdout.flush()
        sys.stdout.write(". ")
        time.sleep(t_anchor/4)
        height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
        last_merged_height_to = int(height_proof_to.var_proofs[0].value)
        # TODO do this with events when available
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
    account_ref = receiver + token_origin
    burn_proof = aergo_from.query_sc_state(
        bridge_from, ["_sv_Burns-" + account_ref],
        root=merge_block_from.blocks_root_hash, compressed=False
    )
    if not burn_proof.verify_proof(merge_block_from.blocks_root_hash):
        raise InvalidMerkleProofError("Unable to verify burn proof")
    if not burn_proof.var_proofs[0].inclusion:
        err = "No tokens deposited for this account reference: {}".format(
            account_ref)
        raise InvalidMerkleProofError(err)
    return burn_proof


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
    balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = burn_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call unlock on aergo_to with the burn proof from aergo_from
    tx, result = aergo_to.call_sc(bridge_to, "unlock",
                                  args=[receiver, balance,
                                        token_origin, ap])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Unlock asset Tx commit failed : {}".format(result))
    time.sleep(COMMIT_TIME)

    result = aergo_to.get_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Unlock asset Tx execution failed : {}".format(result))
    return str(tx.tx_hash)
