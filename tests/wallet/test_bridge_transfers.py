def _test_bridge_transfer(wallet, asset):
    """ test aer/token transfer through merkle bridge and back"""
    amount = 1*10**18
    balance_before, _ = wallet.get_balance(asset, 'mainnet')
    wallet.transfer_to_sidechain('mainnet',
                                 'sidechain2',
                                 asset,
                                 amount)
    wallet.transfer_from_sidechain('sidechain2',
                                   'mainnet',
                                   asset,
                                   amount)
    balance_after, _ = wallet.get_balance(asset, 'mainnet')

    if asset == 'aergo':
        assert balance_before - 2*10**9 == balance_after
    else:
        assert balance_before == balance_after


def test_aer_transfer(wallet):
    return _test_bridge_transfer(wallet, 'aergo')


def test_token_transfer(wallet):
    return _test_bridge_transfer(wallet, 'token1')


def test_delegated_bridge_transfer(wallet):
    """ Presign a token transfer and transfer it via broadcaster for
    a fee.
    """
    asset = 'token1'
    amount = 1*10**18
    initial_balance, _ = wallet.get_balance(asset, 'mainnet')
    owner = wallet.get_wallet_address('default')
    to = wallet.config_data('mainnet', 'bridges', 'sidechain2', 'addr')

    signed_transfer, delegate_data, _ = \
        wallet.get_signed_transfer(amount, to, 'token1', 'mainnet',
                                   fee=1, deadline=0)

    wallet.transfer_to_sidechain('mainnet', 'sidechain2',
                                 asset, amount, sender=owner,
                                 signed_transfer=signed_transfer,
                                 delegate_data=delegate_data,
                                 privkey_name='default2')
    fee_received, _ = wallet.get_balance(asset, 'mainnet',
                                         account_name='default2')
    print("Fee receiver balance = ", fee_received)
    assert fee_received == 1

    to = wallet.config_data('sidechain2', 'bridges', 'mainnet', 'addr')

    signed_transfer, delegate_data, _ = \
        wallet.get_signed_transfer(amount-1, to, 'token1',
                                   'sidechain2', 'mainnet',
                                   fee=1, deadline=0)

    wallet.transfer_from_sidechain('sidechain2', 'mainnet',
                                   asset, amount-1, sender=owner,
                                   signed_transfer=signed_transfer,
                                   delegate_data=delegate_data,
                                   privkey_name='default2')
    fee_received, _ = wallet.get_balance(asset, 'sidechain2', 'mainnet',
                                         account_name='default2')
    print("Fee receiver balance = ", fee_received)
    assert fee_received == 1

    final_balance, _ = wallet.get_balance(asset, 'mainnet')
    assert final_balance == initial_balance - 2
