Deploying a new bridge
======================

Before using the bridge deployer, a config file should be created to register network node connections and 
validators.

.. image:: images/scratch.png

.. code-block:: bash

    $ python3 -m aergo_bridge_operator.bridge_deployer --help                                                                                                                                                                           18h17m ⚑ ◒  

        usage: bridge_deployer.py [-h] -c CONFIG_FILE_PATH --net1 NET1 --net2 NET2
                                --t_anchor1 T_ANCHOR1 --t_final1 T_FINAL1
                                --t_anchor2 T_ANCHOR2 --t_final2 T_FINAL2
                                [--privkey_name PRIVKEY_NAME]

        Deploy bridge contracts between 2 Aergo networks.

        optional arguments:
        -h, --help            show this help message and exit
        -c CONFIG_FILE_PATH, --config_file_path CONFIG_FILE_PATH
                                Path to config.json
        --net1 NET1           Name of Aergo network in config file
        --net2 NET2           Name of Aergo network in config file
        --t_anchor1 T_ANCHOR1
                                Anchoring periode (in Aergo blocks) of net2 on net1
        --t_final1 T_FINAL1   Finality of net2 (in Aergo blocks) root anchored on
                                net1
        --t_anchor2 T_ANCHOR2
                                Anchoring periode (in Aergo blocks) of net1 on net2
        --t_final2 T_FINAL2   Finality of net1 (in Aergo blocks) root anchored on
                                net2
        --privkey_name PRIVKEY_NAME
                                Name of account in config file to sign anchors


    $ python3 -m bridge_operator.bridge_deployer -c './test_config.json' -a 'aergo-local' -e eth-poa-local --t_anchor_aergo 6 --t_final_aergo 4 --t_anchor_eth 7 --t_final_eth 5 --privkey_name "proposer"

        Decrypt exported private key 'proposer'
        Password: 
        ------ DEPLOY BRIDGE BETWEEN mainnet & sidechain2 -----------
        ------ Connect AERGO -----------
        ------ Set Sender Account -----------
        > Sender Address: AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU
        ------ Deploy SC -----------
        validators :  ['AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ']
            > result[G3eppLMXZR29apc8tUie9D8fb19QdB9aYeqHpfRodRzP] : TX_OK
            > result[BfSLueLYFXgXHwDJobMgYakyBgoWyKy6oAo9sQvQdeMn] : TX_OK
        ------ Check deployment of SC -----------
        > SC Address CHAIN1: AmhmKmDGmPSrV6DVckcQbRHmtdf6UjU26L2jY4PCQhWVFopu6zks
        > SC Address CHAIN2: AmfycTw3Qofd31RwwmMQHHbkP1Rf1MUhT8L93JFQkhpynvTZendk
        ------ Store bridge addresses in config.json  -----------
        ------ Disconnect AERGO -----------
