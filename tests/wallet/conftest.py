from wallet.wallet import Wallet

import pytest


@pytest.fixture(scope="session", autouse=True)
def deploy_new_token():
    with open("./contracts/token_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    total_supply = 500*10**6*10**18
    wallet = Wallet("./config.json")
    wallet.deploy_token(payload_str, "token1", total_supply, 'mainnet')


@pytest.fixture(scope="session")
def wallet():
    wallet = Wallet("./config.json")
    return wallet
