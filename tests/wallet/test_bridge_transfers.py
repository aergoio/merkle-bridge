def _test_bridge_transfer(wallet, asset):
    """ test aer/token transfer through merkle bridge and back"""
    amount = 1*10**18
    balance_before, _ = wallet.get_balance(asset, 'mainnet')
    wallet.bridge_transfer('mainnet',
                           'sidechain2',
                           asset,
                           amount,
                           privkey_pwd='1234')
    wallet.bridge_transfer('sidechain2',
                           'mainnet',
                           asset,
                           amount,
                           privkey_pwd='1234')
    balance_after, _ = wallet.get_balance(asset, 'mainnet')

    assert balance_before == balance_after


def test_token_transfer(wallet):
    return _test_bridge_transfer(wallet, 'token1')
