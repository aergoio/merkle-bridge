from aergo_wallet.wallet import AergoWallet

import pytest


@pytest.fixture(scope="session")
def wallet():
    wallet = AergoWallet("./test_config.json")
    return wallet
