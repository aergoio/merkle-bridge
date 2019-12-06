import json
import time
from typing import (
    Tuple,
)

import aergo.herapy as herapy

from aergo.herapy.utils.encoding import (
    decode_b58_check,
)

from aergo_wallet.exceptions import (
    InvalidArgumentsError,
    TxError,
    InvalidMerkleProofError,
)
import logging

logger = logging.getLogger(__name__)

# Wallet utils are made to be used with a custom herapy provider


def get_balance(
    account_addr: str,
    asset_addr: str,
    aergo: herapy.Aergo,
) -> int:
    """ Get an account or the default wallet balance of Aer
    or any token on a given network.
    """
    if not is_aergo_address(account_addr):
        raise InvalidArgumentsError(
            "Account {} must be an Aergo address".format(account_addr)
        )
    balance = 0
    if asset_addr == "aergo":
        # query aergo bits on network_name
        ret_account = aergo.get_account(address=account_addr)
        balance = ret_account.balance
    else:
        balance_q = aergo.query_sc_state(
            asset_addr, ["_sv__balances-" + account_addr]
        )
        if not balance_q.account.state_proof.inclusion:
            raise InvalidArgumentsError(
                "Contract doesnt exist in state, check contract deployed and "
                "chain synced {}".format(balance_q))
        if balance_q.var_proofs[0].inclusion:
            balance = json.loads(balance_q.var_proofs[0].value)['_bignum']
    return int(balance)


def transfer(
    value: int,
    to: str,
    asset_addr: str,
    aergo: herapy.Aergo,
    sender: str,
    fee_limit: int,
    fee_price: int,
) -> str:
    """ Support 3 types of transfers : simple aer transfers, token transfer,
    and signed token transfers (token owner != tx signer)
    """
    if not is_aergo_address(to):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(to)
        )
    aergo.get_account()  # get the latest nonce for making tx
    if asset_addr == "aergo":
        # transfer aer on network_name
        tx, result = aergo.send_payload(to_address=to,
                                        amount=value, payload=None)
    else:
        # transfer token (issued or pegged) on network_name
        tx, result = aergo.call_sc(asset_addr, "transfer",
                                   args=[to, {"_bignum": str(value)}],
                                   amount=0)

    if result.status != herapy.CommitStatus.TX_OK:
        raise TxError("Transfer asset Tx commit failed : {}"
                      .format(result))

    # Check lock success
    result = aergo.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Transfer asset Tx execution failed : {}"
                      .format(result))

    return str(tx.tx_hash)


def bridge_withdrawable_balance(
    account_addr: str,
    asset_address_origin: str,
    bridge_from: str,
    bridge_to: str,
    aergo_from: herapy.Aergo,
    aergo_to: herapy.Aergo,
    deposit_key: str,
    withdraw_key: str,
) -> Tuple[int, int]:
    account_ref = account_addr + asset_address_origin
    # total_deposit : total latest deposit including pending
    _, block_height = aergo_from.get_blockchain_status()
    block_from = aergo_from.get_block_headers(
        block_height=block_height, list_size=1)
    root_from = block_from[0].blocks_root_hash

    deposit_proof = aergo_from.query_sc_state(
        bridge_from, [deposit_key + account_ref],
        root=root_from, compressed=False
    )
    if not deposit_proof.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(deposit_proof))
    total_deposit = 0
    if deposit_proof.var_proofs[0].inclusion:
        total_deposit = int(deposit_proof.var_proofs[0].value
                            .decode('utf-8')[1:-1])

    # get total withdrawn and last anchor height
    withdraw_proof = aergo_to.query_sc_state(
        bridge_to, ["_sv__anchorHeight", withdraw_key + account_ref],
        compressed=False
    )
    if not withdraw_proof.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(withdraw_proof))
    if not withdraw_proof.var_proofs[0].inclusion:
        raise InvalidArgumentsError("Cannot query last anchored height",
                                    withdraw_proof)
    total_withdrawn = 0
    if withdraw_proof.var_proofs[1].inclusion:
        total_withdrawn = int(withdraw_proof.var_proofs[1].value
                              .decode('utf-8')[1:-1])
    last_anchor_height = int(withdraw_proof.var_proofs[0].value)

    # get anchored deposit : total deposit before the last anchor
    block_from = aergo_from.get_block_headers(
        block_height=last_anchor_height, list_size=1)
    root_from = block_from[0].blocks_root_hash
    deposit_proof = aergo_from.query_sc_state(
        bridge_from, [deposit_key + account_ref],
        root=root_from, compressed=False
    )
    if not deposit_proof.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(deposit_proof))
    anchored_deposit = 0
    if deposit_proof.var_proofs[0].inclusion:
        anchored_deposit = int(deposit_proof.var_proofs[0].value
                               .decode('utf-8')[1:-1])
    withdrawable_balance = anchored_deposit - total_withdrawn
    pending = total_deposit - anchored_deposit
    return withdrawable_balance, pending


def wait_finalization(
    aergo: herapy.Aergo
) -> None:
    status = aergo.get_status()
    lib = status.consensus_info.status['LibNo']
    height = status.best_block_height
    time.sleep(height - lib)


def build_deposit_proof(
    aergo_from: herapy.Aergo,
    aergo_to: herapy.Aergo,
    receiver: str,
    bridge_from: str,
    bridge_to: str,
    deposit_height: int,
    token_origin: str,
    key_word: str
) -> herapy.obj.sc_state.SCState:
    """ Check the last anchored root includes the lock and build
    a lock proof for that root
    """
    if not is_aergo_address(receiver):
        raise InvalidArgumentsError(
            "Receiver {} must be an Aergo address".format(receiver)
        )
    # check last merged height
    anchor_info = aergo_to.query_sc_state(bridge_to, ["_sv__anchorHeight"])
    if not anchor_info.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(anchor_info))
    if not anchor_info.var_proofs[0].inclusion:
        raise InvalidArgumentsError("Cannot query last anchored height",
                                    anchor_info)
    last_merged_height_to = int(anchor_info.var_proofs[0].value)
    _, current_height = aergo_to.get_blockchain_status()
    # waite for anchor containing our transfer
    stream = aergo_to.receive_event_stream(bridge_to, "newAnchor",
                                           start_block_no=current_height)
    while last_merged_height_to < deposit_height:
        logger.info(
            "deposit not recorded in current anchor, waiting new anchor "
            "event... / deposit height : %s / last anchor height : %s ",
            deposit_height, last_merged_height_to
        )
        new_anchor_event = next(stream)
        last_merged_height_to = new_anchor_event.arguments[1]
    stream.stop()
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block_headers(
        block_height=last_merged_height_to, list_size=1)
    root_from = merge_block_from[0].blocks_root_hash
    account_ref = receiver + token_origin
    proof = aergo_from.query_sc_state(
        bridge_from, [key_word + account_ref],
        root=root_from, compressed=False
    )
    if not proof.verify_proof(root_from):
        raise InvalidMerkleProofError("Unable to verify {} proof"
                                      .format(key_word))
    if not proof.account.state_proof.inclusion:
        raise InvalidMerkleProofError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(proof))
    if not proof.var_proofs[0].inclusion:
        raise InvalidMerkleProofError(
            "No tokens deposited for this account reference: {}"
            .format(proof))
    return proof


def is_aergo_address(address: str):
    if address[0] != 'A':
        return False
    try:
        decode_b58_check(address)
    except ValueError:
        return False
    if len(address) != 52:
        return False
    return True
