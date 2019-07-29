# Aergo wallet package

## Transfer tokens from mainnet to sidechain and back again
``` py
from aergo_wallet.wallet import AergoWallet

# create a wallet
wallet = AergoWallet("./test_config.json")

amount = 1*10**18
asset = 'token1'
# transfer asset from mainnet to sidechain2
wallet.bridge_transfer('mainnet',
                       'sidechain2',
                       asset,
                       amount)

# transfer asset from sidechain2 to mainnet
wallet.bridge_transfer('sidechain2',
                       'mainnet',
                       asset,
                       amount)
```

## Get balance and transfer assets on a specific network
``` py
from aergo_wallet.wallet import AergoWallet

# create a wallet
wallet = AergoWallet("./test_config.json")

asset = 'token1' # token name or 'aergo' in config.json
balance = wallet.get_balance(account_address, asset_name=asset,
                             network_name='mainnet')

# transfer 2 assets, uses the 'wallet' priv_key by default
wallet.transfer(2*10**18, to_address, asset_name=asset, network_name='mainnet')
```

