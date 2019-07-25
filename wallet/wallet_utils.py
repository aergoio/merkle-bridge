import grpc
import hashlib
import json
import time
from typing import (
    Tuple,
)

import aergo.herapy as herapy

from aergo.herapy.utils.encoding import (
    decode_b58_check,
)
from aergo.herapy.utils.signature import (
    verify_sig,
)

from wallet.exceptions import (
    InvalidArgumentsError,
    TxError,
    InvalidMerkleProofError,
)

from broadcaster.broadcaster_pb2_grpc import (
    BroadcasterStub,
)
from broadcaster.broadcaster_pb2 import (
    SignedTransfer,
)

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
        balance_q = aergo.query_sc_state(asset_addr,
                                         ["_sv_Balances-" +
                                          account_addr]
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
    signed_transfer: Tuple[int, str, str, int] = None
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
        if signed_transfer is not None:
            raise InvalidArgumentsError("cannot make aer signed transfer")

        tx, result = aergo.send_payload(to_address=to,
                                        amount=value, payload=None)
    else:
        # transfer token (issued or pegged) on network_name
        if signed_transfer is not None:
            nonce, sig, fee, deadline = signed_transfer
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

    # Check lock success
    result = aergo.wait_tx_result(tx.tx_hash)
    if result.status != herapy.TxResultStatus.SUCCESS:
        raise TxError("Transfer asset Tx execution failed : {}"
                      .format(result))

    print("Transfer success")
    return str(tx.tx_hash)


def get_signed_transfer(
    value: int,
    to: str,
    asset_addr: str,
    aergo: herapy.Aergo,
    fee: int = 0,
    execute_before: int = 0,
) -> Tuple[Tuple[int, str, str, int], int]:
    """Sign a standard token transfer to be broadcasted by a 3rd party"""
    # calculate deadline
    deadline = 0
    if execute_before != 0:
        _, block_height = aergo.get_blockchain_status()
        deadline = block_height + execute_before
    # get current balance and nonce
    sender = str(aergo.account.address)
    initial_state = aergo.query_sc_state(asset_addr,
                                         ["_sv_Balances-" + sender,
                                          "_sv_Nonces-" + sender,
                                          "_sv_ContractID"
                                          ])
    if not initial_state.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(initial_state))
    balance_p, nonce_p, contractID_p = \
        [item.value for item in initial_state.var_proofs]
    try:
        balance = int(json.loads(balance_p)["_bignum"])
    except json.decoder.JSONDecodeError:
        balance = 0

    try:
        nonce = int(nonce_p)
    except ValueError:
        nonce = 0

    contractID = str(contractID_p[1:-1], 'utf-8')
    msg = bytes(to + ',' + str(value) + ',' + str(nonce) + ',' + str(fee)
                + ',' + str(deadline) + ',' + contractID, 'utf-8')
    h = hashlib.sha256(msg).digest()
    sig = aergo.account.private_key.sign_msg(h).hex()
    signed_transfer = (nonce, sig, str(fee), deadline)
    return signed_transfer, balance


def verify_signed_transfer(
    sender: str,
    receiver: str,
    asset_addr: str,
    amount: int,
    signed_transfer: Tuple[int, str, str, int],
    aergo: herapy.Aergo,
    deadline_margin: int
) -> Tuple[bool, str]:
    """ Verify a signed token transfer is valid:
    - enough balance,
    - nonce is not spent,
    - signature is correct
    - enough time remaining before deadline
    """
    nonce, sig, fee, deadline = signed_transfer
    # get current balance and nonce
    current_state = aergo.query_sc_state(asset_addr,
                                         ["_sv_Balances-" + sender,
                                          "_sv_Nonces-" + sender,
                                          "_sv_ContractID"
                                          ])
    if not current_state.account.state_proof.inclusion:
        raise InvalidArgumentsError(
            "Contract doesnt exist in state, check contract deployed and "
            "chain synced {}".format(current_state))
    balance_p, nonce_p, contractID_p = \
        [item.value for item in current_state.var_proofs]

    # check balance
    try:
        balance = int(json.loads(balance_p)["_bignum"])
    except json.decoder.JSONDecodeError:
        balance = 0
    if amount > balance:
        err = "Insufficient balance"
        return False, err
    # check nonce
    try:
        expected_nonce = int(nonce_p)
    except ValueError:
        expected_nonce = 0
    if expected_nonce != nonce:
        err = "Invalid nonce"
        return False, err
    # check signature
    contractID = str(contractID_p[1:-1], 'utf-8')
    msg = bytes(receiver + ',' + str(amount) + ',' + str(nonce) + ',' + fee
                + ',' + str(deadline) + ',' + contractID, 'utf-8')
    h = hashlib.sha256(msg).digest()
    sig_bytes = bytes.fromhex(sig)
    if not verify_sig(h, sig_bytes, sender):
        err = "Invalid signature"
        return False, err
    # check deadline
    _, best_height = aergo.get_blockchain_status()
    if best_height > deadline - deadline_margin:
        err = "Deadline passed or not enough time to execute"
        return False, err
    return True, ""


def broadcast_transfer(
    broadcaster_ip: str,
    rpc_service: str,
    owner: str,
    token_name: str,
    amount: int,
    signed_transfer: Tuple[int, str, str, int],
    is_pegged: bool = False,
    receiver: str = None
):
    channel = grpc.insecure_channel(broadcaster_ip)
    stub = BroadcasterStub(channel)
    nonce, signature, fee_str, deadline = signed_transfer
    request = SignedTransfer(
        owner=owner, token_name=token_name, amount=str(amount),
        nonce=nonce, signature=signature, fee=fee_str, deadline=deadline,
        is_pegged=is_pegged, receiver=receiver
    )
    return getattr(stub, rpc_service)(request)


def broadcast_simple_transfer(
    broadcaster_ip: str,
    owner: str,
    token_name: str,
    amount: int,
    signed_transfer: Tuple[int, str, str, int],
    is_pegged: bool = False,
    receiver: str = None
):
    return broadcast_transfer(
        broadcaster_ip, "SimpleTransfer", owner, token_name, amount,
        signed_transfer, is_pegged, receiver
    )


def broadcast_bridge_transfer(
    broadcaster_ip: str,
    owner: str,
    token_name: str,
    amount: int,
    signed_transfer: Tuple[int, str, str, int],
    is_pegged: bool = False,
):
    return broadcast_transfer(
        broadcaster_ip, "BridgeTransfer", owner, token_name, amount,
        signed_transfer, is_pegged
    )


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
    block_from = aergo_from.get_block(
        block_height=block_height
    )
    deposit_proof = aergo_from.query_sc_state(
        bridge_from, [deposit_key + account_ref],
        root=block_from.blocks_root_hash, compressed=False
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
        bridge_to, ["_sv_Height", withdraw_key + account_ref],
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
    block_from = aergo_from.get_block(
        block_height=last_anchor_height
    )
    deposit_proof = aergo_from.query_sc_state(
        bridge_from, [deposit_key + account_ref],
        root=block_from.blocks_root_hash, compressed=False
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
    anchor_info = aergo_to.query_sc_state(bridge_to, ["_sv_Height"])
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
    stream = aergo_to.receive_event_stream(bridge_to, "set_root",
                                           start_block_no=current_height)
    while last_merged_height_to < deposit_height:
        print("deposit not recorded in current anchor, waiting new anchor "
              "event... / "
              "deposit height : {} / "
              "last anchor height : {} "
              .format(deposit_height, last_merged_height_to)
              )
        set_root_event = next(stream)
        last_merged_height_to = set_root_event.arguments[0]
    stream.stop()
    # get inclusion proof of lock in last merged block
    merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
    account_ref = receiver + token_origin
    proof = aergo_from.query_sc_state(
        bridge_from, [key_word + account_ref],
        root=merge_block_from.blocks_root_hash, compressed=False
    )
    if not proof.verify_proof(merge_block_from.blocks_root_hash):
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
