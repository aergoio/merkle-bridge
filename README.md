# merkle-bridge
POC implementation of the Aergo Merkle Bridge

## Install
```sh
$ pip install git+ssh://git@github.com/aergoio/herapy.git
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
```sh
$ make bridge
```
### Deploy a new token contract
```sh
$ make deploy_token
```
### Transfer tokens from origin to destination and back
```sh
$ make transfer_to_destination
```
```sh
$ make transfer_to_origin
```


# TODO
- bridge minted contract : requires contract creation withing contract, not yet supported by luavm
- merkle bridge contracts with mp verification and ecverify
- wallet : initiate transfer, create merkle proof, receive minted asset at destination
