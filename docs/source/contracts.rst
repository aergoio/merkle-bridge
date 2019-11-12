Deploying a new bridge
======================

Process
-------
1- Each Validator generates a private key and address to sign bridge messages (anchors, settings update...) and shares the address and validator ip with the bridge Proposer.

2- Proposer creates a config.json file draft. (See `Create a new config file`_ below).

3- Proposer deploys the eth-merkle-bridge.lua contract on bridged networks (See `Deploy the bridge contracts`_ below).

4- Proposer deploys the oracle.lua on both networks and transfers bridge controle to oracles (See `Transfer control of the bridge to the multisig oracle`_ below).

5- Proposer removes his private key registered in config.json, and shares config.json with Validators.

6- Each Validator adds his private key to his config.json.

7- The Validators start validating (see validator docs) with the correct validator index (see position of validator in config.json).

8- Proposer starts operating the bridge (see proposer docs).


Create a new config file
------------------------
A config file can be created with the cli tool or manually.

.. image:: images/scratch.png


Deploy the bridge contracts
---------------------------
The sender of the deployment tx will be the bridge owner. Ownership is then transfered to the multisig oracle.

.. code-block:: bash

    $ python3 -m aergo_bridge_operator.bridge_deployer --help

        usage: bridge_deployer.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2
                                [--privkey_name PRIVKEY_NAME] [--local_test]

        Deploy bridge contracts between 2 Aergo networks.

        optional arguments:
        -h, --help            show this help message and exit
        -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                                Path to config.json
        --net1 NET1           Name of Aergo network in config file
        --net2 NET2           Name of Aergo network in config file
        --privkey_name PRIVKEY_NAME
                                Name of account in config file to sign anchors
        --local_test          Start all validators locally for convenient testing


    $ python3 -m aergo_bridge_operator.bridge_deployer -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer"

        DEPLOY BRIDGE
        Decrypt exported private key 'proposer'
        Password: 
        ------ DEPLOY BRIDGE BETWEEN mainnet & sidechain2 -----------
        ------ Connect AERGO -----------
        ------ Set Sender Account -----------
        > Sender Address: AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU
        ------ Deploy SC -----------
            > result[G412HSrJUKbEL3P5QLuXn7mt5DxkGvdwMgmdujQz1w3W] : TX_OK
            > result[HVtjZC4r3fB3PYztJjLsmnfdnA29i17aJHLVwebYoX2v] : TX_OK
        ------ Check deployment of SC -----------
        > Bridge Address mainnet: AmgQqVWX3JADRBEVkVCM4CyWdoeXuumeYGGJJxEeoAukRC26hxmw
        > Bridge Address sidechain2: AmgQqVWX3JADRBEVkVCM4CyWdoeXuumeYGGJJxEeoAukRC26hxmw
        ------ Store bridge addresses in config.json  -----------
        ------ Disconnect AERGO -----------


Transfer control of the bridge to the multisig oracle
-----------------------------------------------------

The oracle_deployer script will deploy the oracle contract (with validators previously registered in config.json),
and transfer ownership to the newly deployed contract.

.. code-block:: bash

    $ python3 -m aergo_bridge_operator.oracle_deployer --help

        DEPLOY ORACLE
        usage: oracle_deployer.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2
                                [--privkey_name PRIVKEY_NAME] [--local_test]

        Deploy oracle contracts to controle the bridge between 2 Aergo networks.

        optional arguments:
        -h, --help            show this help message and exit
        -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                                Path to config.json
        --net1 NET1           Name of Aergo network in config file
        --net2 NET2           Name of Aergo network in config file
        --privkey_name PRIVKEY_NAME
                                Name of account in config file to sign anchors
        --local_test          Start all validators locally for convenient testing

    $ python3 -m aergo_bridge_operator.oracle_deployer -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer"

        DEPLOY ORACLE
        Decrypt exported private key 'proposer'
        Password: 
        ------ DEPLOY ORACLE BETWEEN mainnet & sidechain2 -----------
        ------ Connect AERGO -----------
        ------ Set Sender Account -----------
        > Sender Address: AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU
        ------ Deploy SC -----------
        validators :  ['AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ']
            > result[GG6THEXUbmj6E2SDxVri67iF1ExLeUoS5WRgCi5vH5zF] : TX_OK
            > result[42dqiZrkb5tn6tDiNGL2ePdAd6akoVs3LVYytuD7iNR9] : TX_OK
        ------ Check deployment of SC -----------
        > Oracle Address mainnet: AmhXrQ7KdNA4naBi2sTwHj13aBzVBohRhxy262nXsPbV2YbULXUR
        > Oracle Address sidechain2: AmhXrQ7KdNA4naBi2sTwHj13aBzVBohRhxy262nXsPbV2YbULXUR
        ------ Store bridge addresses in config.json  -----------
        ------ Transfer bridge control to oracles -----------
        ------ Disconnect AERGO -----------
