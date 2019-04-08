def _test_transfer(wallet, asset, fee=0):
    """ Basic token/aer transfer on it's native chain."""
    to = wallet.get_wallet_address('receiver')
    amount = 2

    to_balance, _ = wallet.get_balance(asset, 'mainnet',
                                       account_name='receiver')
    print('receiver balance before', to_balance)
    from_balance, _ = wallet.get_balance(asset, 'mainnet')
    print('sender balance before', from_balance)

    wallet.transfer(amount, to, asset, 'mainnet', privkey_pwd='1234')

    to_balance_after, _ = wallet.get_balance(asset, 'mainnet',
                                             account_name='receiver')
    print('receiver balance after', to_balance_after)
    from_balance_after, _ = wallet.get_balance(asset, 'mainnet')
    print('sender balance after', from_balance_after)

    assert to_balance_after == to_balance + amount
    assert from_balance_after == from_balance - amount - fee


def test_aer_transfer(wallet):
    return _test_transfer(wallet, 'aergo', fee=0)


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
                                 amount,
                                 privkey_pwd='1234')

    to_balance, _ = wallet.get_balance(asset, 'sidechain2',
                                       asset_origin_chain='mainnet',
                                       account_name='receiver')
    print('receiver balance before', to_balance)
    from_balance, _ = wallet.get_balance(asset, 'sidechain2',
                                         asset_origin_chain='mainnet')
    print('sender balance before', from_balance)

    wallet.transfer(amount, to, asset, 'sidechain2',
                    asset_origin_chain='mainnet', privkey_pwd='1234')

    to_balance_after, _ = wallet.get_balance(asset, 'sidechain2',
                                             asset_origin_chain='mainnet',
                                             account_name='receiver')
    print('receiver balance after', to_balance_after)
    from_balance_after, _ = wallet.get_balance(asset, 'sidechain2',
                                               asset_origin_chain='mainnet')
    print('sender balance after', from_balance_after)

    assert to_balance_after == to_balance + amount
    assert from_balance_after == from_balance - amount
