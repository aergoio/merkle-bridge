# merkle-bridge
POC implementation of the Aergo Merkle Bridge

## Install
```sh
$ cd merkle-bridge/
$ virtualenv -p python3 venv
$ source venv/bin/activate
$ make install
```

## Operate the merkle bridge
### Start aergo nodes
Setup a node for each blockchain to bridge and update config.json.
For a quickstart test, start two --testmode nodes locally with docker
```sh
$ make docker
```
### Compiling contracts (optional)
The contracts are already compiled, but to recompile with a local aergoluac :
```sh
$ make compile_bridge
$ make compile_token
```
### Deploy merkle bridge contracts
```sh
$ make deploy_bridge
```
### Start the bridge operator
#### Start the bridge proposer
```sh
$ make proposer
```
#### Start the bridge validators
```sh
$ make validator
```

### Deploy a new token contract
```py
from wallet.wallet import Wallet

# load config file that stores network ip, asset addresses...
with open("./config.json", "r") as f:
    c = json.load(f)

# create a wallet
wallet = Wallet(c)

total_supply = 500*10**18
# deploy the token and stored the address in config.json
wallet.deploy_token(p, "token_name", total_supply)
```

### Transfer tokens from mainnet to sidechain and back again
```py
from wallet.wallet import Wallet

# load config file that stores network ip, asset addresses...
with open("./config.json", "r") as f:
    c = json.load(f)

# create a wallet
wallet = Wallet(c)

amount = 1*10**18
asset = 'aergo'
# transfer aergo from mainnet to sidechain2
wallet.transfer_to_sidechain('mainnet',
                             'sidechain2',
                             asset,
                             amount)

# transfer minted aergo from sidechain2 mainnet
wallet.transfer_from_sidechain('sidechain2',
                               'mainnet',
                               asset,
                               amount)
```
