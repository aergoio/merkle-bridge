from wallet.wallet_utils import (
    transfer
)
from wallet.exceptions import (
    TxError
)
import pytest


def test_transfer_to_sidechain_broadcast(wallet):
    asset = 'token1'
    amount = 100*10**18
    fee = 2*10**18
    initial_balance, _ = wallet.get_balance(asset, 'mainnet')
    initial_balance_broadcaster, _ = wallet.get_balance(
        asset, 'mainnet', account_name='broadcaster'
    )
    wallet.d_bridge_transfer(
        "mainnet", "sidechain2", "token1", amount, fee,
        privkey_pwd='1234'
    )
    after_balance, _ = wallet.get_balance(asset, 'mainnet')
    after_balance_to, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet')
    after_balance_broadcaster, _ = wallet.get_balance(
        asset, 'mainnet', account_name='broadcaster'
    )
    assert after_balance == initial_balance - amount - fee
    assert after_balance_broadcaster == initial_balance_broadcaster + fee

    initial_broadcaster_balance_to, _ = wallet.get_balance(
        asset, 'sidechain2', 'mainnet', account_name='broadcaster'
    )

    wallet.d_bridge_transfer(
        "sidechain2", "mainnet", "token1", amount - fee, fee,
        privkey_pwd='1234'
    )

    final_balance, _ = wallet.get_balance(asset, 'mainnet')
    final_balance_to, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet')
    final_balance_broadcaster, _ = wallet.get_balance(
        asset, 'sidechain2', 'mainnet', account_name='broadcaster'
    )

    assert final_balance_to == after_balance_to - amount
    assert final_balance_broadcaster == initial_broadcaster_balance_to + fee
    assert final_balance == initial_balance - 2*fee


def test_simple_transfer_broadcast(wallet):
    asset = 'token1'
    amount = 100*10**18
    fee = 2*10**18
    # test delegated transfer of a pegged token
    wallet.d_transfer_to_sidechain('mainnet', 'sidechain2', asset, amount,
                                   fee, privkey_pwd='1234')
    balance_before, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet',
                                           'default2')
    balance_before_br, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet',
                                              'broadcaster')
    default2 = wallet.get_wallet_address('default2')
    wallet.d_transfer(amount - fee, fee, default2, asset, 'sidechain2',
                      'mainnet', 'default', '1234')
    balance, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet', 'default2')
    assert balance == balance_before + amount - fee
    balance, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet',
                                    'broadcaster')
    assert balance == balance_before_br + fee

    # test delegated transfer on origin chain
    balance_before, _ = wallet.get_balance(asset, 'mainnet',
                                           account_name='default2')
    balance_before_br, _ = wallet.get_balance(asset, 'mainnet',
                                              account_name='broadcaster')
    default2 = wallet.get_wallet_address('default2')
    wallet.d_transfer(amount, fee, default2, asset, 'mainnet',
                      privkey_pwd='1234')
    balance, _ = wallet.get_balance(asset, 'mainnet',
                                    account_name='default2')
    assert balance == balance_before + amount
    balance, _ = wallet.get_balance(asset, 'mainnet',
                                    account_name='broadcaster')
    assert balance == balance_before_br + fee


def test_verify_signed_transfer(wallet):
    amount = 2
    to = wallet.get_wallet_address('receiver')
    fee = 1
    asset = 'token1'
    sender = wallet.get_wallet_address('default')
    signed_transfer, _ = wallet.get_signed_transfer(
        amount, to, asset, 'mainnet', fee=fee, execute_before=10,
        privkey_pwd='1234'
    )
    valid, _ = wallet.verify_signed_transfer(
        amount, sender, to, asset, 'mainnet', signed_transfer, 5
    )
    assert valid
    # bump the nonce by transfering
    wallet.transfer(amount, to, asset, 'mainnet', privkey_pwd='1234')
    valid, err = wallet.verify_signed_transfer(
        amount, sender, to, asset, 'mainnet', signed_transfer, 5
    )
    assert not valid
    assert err == "Invalid nonce"
    # test deadline too short
    signed_transfer, _ = wallet.get_signed_transfer(
        amount, to, asset, 'mainnet', fee=fee, execute_before=1,
        privkey_pwd='1234'
    )
    valid, err = wallet.verify_signed_transfer(
        amount, sender, to, asset, 'mainnet', signed_transfer, 5
    )

    assert not valid
    assert err == "Deadline passed or not enough time to execute"


def test_broadcaster_cannot_burn_signed_transfer_to_sidechain(wallet):
    amount = 2
    to = wallet.config_data(
        'networks', 'mainnet', 'bridges', 'sidechain2', 'addr')
    fee = 1
    asset = 'token1'
    token_addr = wallet.config_data(
        'networks', 'mainnet', 'tokens', asset, 'addr')
    aergo = wallet.get_aergo('mainnet', 'default2', privkey_pwd='1234')
    owner = wallet.get_wallet_address('default')
    signed_transfer, _ = wallet.get_signed_transfer(
        amount, to, asset, 'mainnet', fee=fee, execute_before=10,
        privkey_name='default', privkey_pwd='1234'
    )
    with pytest.raises(TxError):
        transfer(amount, to, token_addr, aergo, owner,
                 0, 0, signed_transfer)
