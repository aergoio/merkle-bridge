# Bridge operator package

## Proposer

``` sh
$ python3 -m aergo_bridge_operator.proposer_client --help

usage: proposer_client.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2
                          [--privkey_name PRIVKEY_NAME] [--auto_update]

Start a proposer between 2 Aergo networks.

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                        Path to config.json
  --net1 NET1           Name of Aergo network in config file
  --net2 NET2           Name of Aergo network in config file
  --privkey_name PRIVKEY_NAME
                        Name of account in config file to sign anchors
  --auto_update         Update bridge contract when settings change in config
                        file
$ python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --auto_update
```

``` py
from aergo_bridge_operator.proposer_client import BridgeProposerClient

proposer = BridgeProposerClient("./test_config.json", 'mainnet', 'sidechain2')
proposer.run()
```

## Validator

``` sh
$ python3 -m aergo_bridge_operator.validator_server --help

usage: validator_server.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2 -i
                           VALIDATOR_INDEX [--privkey_name PRIVKEY_NAME]
                           [--auto_update] [--local_test]

Start a validator between 2 Aergo networks.

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                        Path to config.json
  --net1 NET1           Name of Aergo network in config file
  --net2 NET2           Name of Aergo network in config file
  -i VALIDATOR_INDEX, --validator_index VALIDATOR_INDEX
                        Index of the validator in the ordered list of
                        validators
  --privkey_name PRIVKEY_NAME
                        Name of account in config file to sign anchors
  --auto_update         Update bridge contract when settings change in config
                        file
  --local_test          Start all validators locally for convenient testing 

$ python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --auto_update
```

``` py
from aergo_bridge_operator.validator_server import ValidatorServer

validator = ValidatorServer("./test_config.json", 'mainnet', 'sidechain2')
validator.run()
```
