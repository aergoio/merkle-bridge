import pytest

from wallet.exceptions import TxError


def _test_transfer(wallet, asset, fee=0):
    """ Basic token/aer transfer on it's native chain."""
    to = wallet.get_wallet_address('receiver')
    amount = 2

    to_balance, _ = wallet.get_balance(asset, 'mainnet',
                                       account_name='receiver')
    print('receiver balance before', to_balance)
    from_balance, _ = wallet.get_balance(asset, 'mainnet')
    print('sender balance before', from_balance)

    wallet.transfer(amount, to, asset, 'mainnet')

    to_balance_after, _ = wallet.get_balance(asset, 'mainnet',
                                             account_name='receiver')
    print('receiver balance after', to_balance_after)
    from_balance_after, _ = wallet.get_balance(asset, 'mainnet')
    print('sender balance after', from_balance_after)

    assert to_balance_after == to_balance + amount
    assert from_balance_after == from_balance - amount - fee


def test_aer_transfer(wallet):
    return _test_transfer(wallet, 'aergo', fee=1*10**9)


def test_token_transfer(wallet):
    return _test_transfer(wallet, 'token1')


def test_transfer_pegged_token(wallet):
    """ Pegged token transfer on sidechain."""
    to = wallet.get_wallet_address('receiver')
    asset = 'token1'
    amount = 2

    # give funds to sender on the sidechain
    wallet.transfer_to_sidechain('mainnet',
                                 'sidechain2',
                                 asset,
                                 amount)

    to_balance, _ = wallet.get_balance(asset, 'sidechain2',
                                       asset_origin_chain='mainnet',
                                       account_name='receiver')
    print('receiver balance before', to_balance)
    from_balance, _ = wallet.get_balance(asset, 'sidechain2',
                                         asset_origin_chain='mainnet')
    print('sender balance before', from_balance)

    wallet.transfer(amount, to, asset, 'sidechain2',
                    asset_origin_chain='mainnet')

    to_balance_after, _ = wallet.get_balance(asset, 'sidechain2',
                                             asset_origin_chain='mainnet',
                                             account_name='receiver')
    print('receiver balance after', to_balance_after)
    from_balance_after, _ = wallet.get_balance(asset, 'sidechain2',
                                               asset_origin_chain='mainnet')
    print('sender balance after', from_balance_after)

    assert to_balance_after == to_balance + amount
    assert from_balance_after == from_balance - amount


def test_delegated_transfer(wallet):
    """ Delegated token transfer : send a presigned token transfer
    and collect a fee. """
    asset = 'token1'
    amount = 2
    fee = 1
    to = wallet.get_wallet_address('receiver')
    sender = wallet.get_wallet_address('default')

    from_balance, _ = wallet.get_balance(asset, 'mainnet')
    print('sender balance before', from_balance)
    to_balance, _ = wallet.get_balance(asset, 'mainnet',
                                       account_name='receiver')
    print('receiver balance before', to_balance)
    broadcaster_balance, _ = wallet.get_balance(asset, 'mainnet',
                                                account_name='default2')
    print('broadcaster balance before', broadcaster_balance)

    # sign transfer with default wallet

    with pytest.raises(TxError):
        # test deadline passed
        signed_transfer, delegate_data, balance = wallet.get_signed_transfer(
            amount, to, 'token1', 'mainnet', fee=1, deadline=1)

        # broadcast transaction with a different wallet and collect the fee
        wallet.transfer(amount, to, asset, 'mainnet', privkey_name='default2',
                        sender=sender, signed_transfer=signed_transfer,
                        delegate_data=delegate_data)
    signed_transfer, delegate_data, balance = wallet.get_signed_transfer(
        amount, to, 'token1', 'mainnet', fee=1, deadline=0)

    # broadcast transaction with a different wallet and collect the fee
    wallet.transfer(amount, to, asset, 'mainnet', privkey_name='default2',
                    sender=sender, signed_transfer=signed_transfer,
                    delegate_data=delegate_data)

    broadcaster_balance_after, _ = wallet.get_balance(asset, 'mainnet',
                                                      account_name='default2')
    print('broadcaster balance after', broadcaster_balance_after)
    to_balance_after, _ = wallet.get_balance(asset, 'mainnet',
                                             account_name='receiver')
    print('receiver balance after', to_balance_after)
    from_balance_after, _ = wallet.get_balance(asset, 'mainnet',
                                               account_name='default')
    print('sender balance after', from_balance_after)

    assert from_balance_after == from_balance - amount - fee
    assert to_balance_after == to_balance + amount
    assert broadcaster_balance_after == broadcaster_balance + fee
