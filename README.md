# merkle-bridge

[![Build Status](https://travis-ci.org/aergoio/merkle-bridge.svg?branch=master)](https://travis-ci.org/aergoio/merkle-bridge)

POC implementation of the Aergo Merkle Bridge

https://merkle-bridge.readthedocs.io/en/latest/index.html

This repository contains :
* Bridge contracts
* A proposal for standard tokens on Aergo (necessary for bridge compatibility)


* Bridge operator:
  * Proposer
  * Validator
  * BridgeSettingsManager
  * Bridge deployer script


* Wallet
  * Transfer tokens and aergo on any Aergo network
  * Transfer tokens and aergo **between** Aergo networks
  * Query balances
  * Query pending sidechain withdrawals
  * Sign delegated token transfers to use with a tx broadcaster
  * Deploy tokens
  * Handle encrypted private keys


* Transaction broadcaster : allows users to make token transfers without paying aer fees.

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
$ python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --auto_update
```

### Validator
Start a validator between 2 Aergo networks.
```sh
$ python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --auto_update
```

## Running tests
Start 2 test networks
```sh
$ make docker
```

Deploy bridge on mainnet and sidechain
```sh
$ make deploy_bridge
```
Deploy a new test token on mainnet
```sh
$ make deploy_token
```
In a new terminal : start proposer
```sh
$ make proposer
```
In a new terminal : start validator
```sh
$ make validator
```
In a new terminal : start broadcaster
```sh
$ make broadcaster
```
In a new terminal : test wallet transfers, bridge transfers, delegated transfers and the bridge multisig
```sh
$ python3 -m pytest -s tests/
```
Remove test networks data
```sh
$ make clean
```
