def _test_bridge_transfer(wallet, asset):
    """ test aer/token transfer through merkle bridge and back"""
    amount = 1*10**18
    balance_before, _ = wallet.get_balance(asset, 'mainnet')
    wallet.transfer_to_sidechain('mainnet',
                                 'sidechain2',
                                 asset,
                                 amount,
                                 privkey_pwd='1234')
    wallet.transfer_from_sidechain('sidechain2',
                                   'mainnet',
                                   asset,
                                   amount,
                                   privkey_pwd='1234')
    balance_after, _ = wallet.get_balance(asset, 'mainnet')

    if asset == 'aergo':
        assert balance_before - 2*10**9 == balance_after
    else:
        assert balance_before == balance_after


def test_aer_transfer(wallet):
    return _test_bridge_transfer(wallet, 'aergo')


def test_token_transfer(wallet):
    return _test_bridge_transfer(wallet, 'token1')
