# merkle-bridge

[![Build Status](https://travis-ci.org/aergoio/merkle-bridge.svg?branch=master)](https://travis-ci.org/aergoio/merkle-bridge)

POC implementation of the Aergo Merkle Bridge

https://merkle-bridge.readthedocs.io/en/latest/index.html


* Bridge operator:
  * Proposer
  * Validator
  * Bridge deployer script


* Wallet
  * Transfer tokens and aergo on any Aergo network
  * Transfer tokens and aergo **between** Aergo networks
  * Query balances
  * Query pending sidechain withdrawals
  * Deploy tokens
  * Handle encrypted private keys


The operators and wallet both use a **config.json** file to operate. This file records, network names and ip, token addresses, pegged token addresses, bridge addresses, validators and proposer information (ip and address), wallet encrypted private keys.

## Install
```sh
$ cd merkle-bridge/
$ virtualenv -p python3 venv
$ source venv/bin/activate
$ pip install -r requirements.txt
```

Optional dev dependencies (lint, testing...)
```sh
$ pip install -r dev-dependencies.txt
```

## CLI
The CLI can generate new config.json files, perform cross chain asset transfers and query balances and pending transfer amounts. 
```sh
$ python3 -m aergo_cli.main
```

## Bridge Operator
### Proposer
Start a proposer between 2 Aergo networks.
```sh
$ python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --anchoring_on
```

### Validator
Start a validator between 2 Aergo networks.
```sh
$ python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --anchoring_on
```

## Running tests
Start 2 test networks
```sh
$ make docker
```

Deploy test bridge, oralces and token on mainnet and sidechain
```sh
$ make deploy_test_bridge
```
In a new terminal : start validator
```sh
$ make validator
```
In a new terminal : start proposer
```sh
$ make proposer
```
In a new terminal : test wallet transfers, bridge transfers, delegated transfers and the bridge multisig
```sh
$ make tests
```
Remove test networks data
```sh
$ make clean
```
