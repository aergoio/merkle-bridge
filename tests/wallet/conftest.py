from wallet.wallet import Wallet

import pytest


@pytest.fixture(scope="session")
def wallet():
    wallet = Wallet("./config.json")
    return wallet
