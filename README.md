# merkle-bridge
POC implementation of the Aergo Merkle Bridge

## Install
```sh
$ pip install git+ssh://git@github.com/aergoio/herapy.git
```

## Operate the merkle bridge
### Start aergo nodes
Run a node for each blockchain the bridge is connecting to and set the port in the configuration file.
### Deploy merkle bridge contracts
Transfer funds to the account used to send transactions.

The Lua contract is already compiled and will be deployed with :
```sh
$ make deploy
```
### Start the bridge operator
```sh
$ make bridge
```
### Transfer tokens from origin to destination and back
```sh
$ make transfer_to_destination
```
```sh
$ make transfer_to_origin
```


# TODO
- merkle bridge contracts
- contract deployer, writes addresses to a file accessible by wallet
- operator : regular checkpointing of state roots on each side of the bridge
- wallet : initiate transfer, create merkle proof, receive minted asset at destination
