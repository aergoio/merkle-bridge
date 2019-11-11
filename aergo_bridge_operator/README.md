# Bridge operator package

## Proposer

``` sh
$ python3 -m aergo_bridge_operator.proposer_client --help

    usage: proposer_client.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2
                            [--privkey_name PRIVKEY_NAME] [--anchoring_on]
                            [--auto_update] [--oracle_update] [--local_test]

    Start a proposer between 2 Aergo networks.

    optional arguments:
    -h, --help            show this help message and exit
    -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                            Path to config.json
    --net1 NET1           Name of Aergo network in config file
    --net2 NET2           Name of Aergo network in config file
    --privkey_name PRIVKEY_NAME
                            Name of account in config file to sign anchors
    --anchoring_on        Enable anchoring (can be diseabled when wanting to
                            only update settings)
    --auto_update         Update bridge contract when settings change in config
                            file
    --oracle_update       Update bridge contract when validators or oracle addr
                            change in config file
    --local_test          Start proposer with password for testing


$ python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --anchoring_on
```

``` py
from aergo_bridge_operator.proposer_client import BridgeProposerClient

proposer = BridgeProposerClient(
    "./test_config.json", 'mainnet', 'sidechain2', privkey_name='proposer,
    anchoring_on=True
)
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

$ python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --anchoring_on
```

``` py
from aergo_bridge_operator.validator_server import ValidatorServer

validator = ValidatorServer(
    "./test_config.json", 'mainnet', 'sidechain2', privkey_name='validator',
    validator_index=2, anchoring_on=True
)
validator.run()
```
