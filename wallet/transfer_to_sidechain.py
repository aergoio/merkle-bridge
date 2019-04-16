import json
import sys
import time

from typing import (
    Tuple,
    Union,
)

import aergo.herapy as herapy

from wallet.exceptions import (
    InvalidMerkleProofError,
    TxError,
    InvalidArgumentsError,
)

COMMIT_TIME = 3


def lock(
    aergo_from: herapy.Aergo,
    bridge_from: str,
    receiver: str,
    value: int,
    asset: str,
    fee_limit: int,
    fee_price: int,
    signed_transfer: Union[Tuple[int, str], Tuple[int, str, str, int]] = None,
) -> Tuple[int, str]:
    """ Lock can be called to lock aer or tokens.
        it supports delegated transfers when tx broadcaster is not
        the same as the token owner
    """
    if asset == "aergo":
        tx, result = aergo_from.call_sc(bridge_from, "lock",
                                        args=[receiver, str(value), asset],
                                        amount=value)
    else:
        if signed_transfer is None:
            raise InvalidArgumentsError("""provide signature
                                        and nonce for token transfers""")
        args = (receiver, str(value), asset) + signed_transfer
        tx, result = aergo_from.call_sc(bridge_from, "lock",
                                        args=args,
                                        amount=0)
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Lock asset Tx commit failed : {}".format(result))
    time.sleep(COMMIT_TIME)

    # Check lock success
    result = aergo_from.get_tx_result(tx.tx_hash)
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
    t_anchor: int
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the lock and build
    a lock proof for that root
    """
    # check last merged height
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    last_merged_height_to = int(height_proof_to.var_proofs[0].value)
    # waite for anchor containing our transfer
    if last_merged_height_to < lock_height:
        sys.stdout.write("waiting new anchor ")
    while last_merged_height_to < lock_height:
        sys.stdout.flush()
        sys.stdout.write(". ")
        time.sleep(t_anchor/4)
        height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
        last_merged_height_to = int(height_proof_to.var_proofs[0].value)
        # TODO do this with events when available -> wait for the next set_root
        # event to be sure there is enough time for minting.
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
    account_ref = receiver + token_origin
    lock_proof = aergo_from.query_sc_state(
        bridge_from, ["_sv_Locks-" + account_ref],
        root=merge_block_from.blocks_root_hash, compressed=False
    )
    if not lock_proof.verify_proof(merge_block_from.blocks_root_hash):
        raise InvalidMerkleProofError("Unable to verify lock proof")
    if not lock_proof.var_proofs[0].inclusion:
        err = "No tokens deposited for this account reference: {}".format(
            account_ref)
        raise InvalidMerkleProofError(err)
    return lock_proof


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
    balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
    auditPath = lock_proof.var_proofs[0].auditPath
    ap = [node.hex() for node in auditPath]
    # call mint on aergo_to with the lock proof from aergo_from
    tx, result = aergo_to.call_sc(bridge_to, "mint",
                                  args=[receiver, balance,
                                        token_origin, ap])
    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Mint asset Tx commit failed : {}".format(result))
    time.sleep(COMMIT_TIME)

    result = aergo_to.get_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Mint asset Tx execution failed : {}".format(result))
    token_pegged = json.loads(result.detail)[0]
    return token_pegged, str(tx.tx_hash)
