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
    receiver: str,
    value: int,
    token_pegged: str,
    bridge_from: str,
    signed_transfer: Tuple[int, str] = None,
    delegate_data: Tuple[str, int] = None
) -> int:
    """ Burn a minted token on a sidechain. """
    if signed_transfer is not None and delegate_data is not None:
        nonce, sig = signed_transfer
        fee, deadline = delegate_data
        args = [receiver, str(value), token_pegged, nonce, sig, fee, deadline]
        tx, result = aergo_from.call_sc(bridge_from, "burn", args=args)
    else:
        tx, result = aergo_from.call_sc(bridge_from, "burn",
                                        args=[receiver, str(value),
                                              token_pegged])

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

    print("Burn success : ", result.detail)
    return burn_height


def build_burn_proof(
    aergo_to: herapy.Aergo,
    aergo_from: herapy.Aergo,
    receiver: str,
    bridge_to: str,
    bridge_from: str,
    burn_height: int,
    token_origin: str,
    t_anchor: int,
    t_final: int
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the burn and build
    a burn proof for that root
    """
    # check last merged height
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    last_merged_height_to = int(height_proof_to.var_proofs[0].value)
    # waite for anchor containing our transfer
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
    return burn_proof


def unlock(
    aergo_to: herapy.Aergo,
    receiver: str,
    burn_proof: herapy.obj.sc_state.SCState,
    token_origin: str,
    bridge_to: str
) -> None:
    """ Unlock the receiver's deposit balance on aergo_to. """
    balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = burn_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo_from with the lock proof from aergo_to
    tx, result = aergo_to.call_sc(bridge_to, "unlock",
                                  args=[receiver, balance,
                                        token_origin, ap])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Unlock asset Tx commit failed : {}".format(result))

    time.sleep(COMMIT_TIME)
    result = aergo_to.get_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Unlock asset Tx execution failed : {}".format(result))

    print("Unlock success on origin : ", result.detail)
