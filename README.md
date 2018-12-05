# merkle-bridge
POC implementation of the Aergo Merkle Bridge

## Install
```sh
$ pip install git+ssh://git@github.com/aergoio/herapy.git
```

## Operate the merkle bridge
### Start aergo nodes
Setup a node for each blockchain to bridge.
You can build nodes locally and set ports according to the config file. Or simply start nodes with docker :
```sh
$ make docker
```
### Compiling contracts (optional)
The contracts are already compiled, but to recompile with a local aergoluac :
```sh
$ make compile
```
### Deploy merkle bridge contracts
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
- docker nodes
- config file
- aergo token contract
- bridge minted contract : requires contract creation withing contract, not yet supported by luavm
- merkle bridge contracts : merkle proof and signature verification not yet supported by luavm
- wallet : initiate transfer, create merkle proof, receive minted asset at destination
