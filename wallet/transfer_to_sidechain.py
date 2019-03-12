import json
import sys
import time

import aergo.herapy as herapy

from wallet.exceptions import (
    InvalidMerkleProofError,
    TxError,
    InvalidArgumentsError,
)

COMMIT_TIME = 3


def lock(
    aergo_from,
    bridge_from,
    receiver,
    value,
    asset,
    signed_transfer=None,
    delegate_data=None
):
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
        args = [receiver, str(value), asset] + signed_transfer
        if delegate_data is not None:
            args = args + delegate_data
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

    print("Lock success : ", result.detail)
    return lock_height


def build_lock_proof(
    aergo_from,
    aergo_to,
    receiver,
    bridge_from,
    bridge_to,
    lock_height,
    token_origin,
    t_anchor,
    t_final
):
    """ Check the last anchored root includes the lock and build
    a lock proof for that root
    """
    # check last merged height
    height_proof_to = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
    last_merged_height_to = int(height_proof_to.var_proofs[0].value)
    # waite for anchor containing our transfer
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
    return lock_proof


def mint(
    aergo_to,
    receiver,
    lock_proof,
    token_origin,
    bridge_to
):
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
    print("Mint success : ", result.detail)
    return token_pegged
