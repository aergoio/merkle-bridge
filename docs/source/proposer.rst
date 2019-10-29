Proposer
========

A proposer connects to all validators and requests them to sign a new anchor 
with the GetAnchorSignature rpc request.
To prevent downtime, anybody can become a proposer and request signatures to validators.
It is the validator's responsibility to only sign correct anchors.
The bridge contracts will not update the state root if the anchoring time is not reached (t_anchor).


Starting a Proposer
--------------------


.. code-block:: bash

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

        proposer: MainThread: "mainnet Validators: ['AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ']"
        proposer: MainThread: "sidechain2 (t_final=4) -> mainnet  : t_anchor=7"
        proposer: MainThread: "Set Sender Account"
        proposer: MainThread: "mainnet Proposer Address: AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU"
        proposer: MainThread: "sidechain2 Validators: ['AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ', 'AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ']"
        proposer: MainThread: "mainnet (t_final=5) -> sidechain2  : t_anchor=7"
        proposer: MainThread: "Set Sender Account"
        proposer: MainThread: "sidechain2 Proposer Address: AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU"
        proposer: sidechain2: "Current mainnet -> sidechain2 ⚓ anchor: height: 3585, root: 0x0x4abe990463eeaf2ebb98971c5358bf0a1e8e33cbc8a75c05222cb324cd503705, nonce: 245"
        proposer: mainnet: "Current sidechain2 -> mainnet ⚓ anchor: height: 3585, root: 0x0x5b5b2ebddf46829d05ba0efbc756c53dbd6603413c9557e3d720e8d5c37ccf94, nonce: 315"
        proposer: sidechain2: "🖋 Gathering validator signatures for: root: 0x36b7ed1f97ff9fb4af052d3c36a80a00961f0e0be569d8012a08678dc8d27a98, height: 3604'"
        proposer: mainnet: "🖋 Gathering validator signatures for: root: 0x3bd469d09fdc0e195063b811c59e88c4d72af53f69d85b783927c76aac34d4cc, height: 3605'"
        proposer: mainnet: "⚓ Anchor success, ⏰ wait until next anchor time: 7s..."
        proposer: sidechain2: "⚓ Anchor success, ⏰ wait until next anchor time: 7s..."



.. code-block:: python

    from aergo_bridge_operator.proposer_client import BridgeProposerClient

    proposer = BridgeProposerClient("./test_config.json", 'mainnet', 'sidechain2')
    proposer.run()


Updating bridge settings
------------------------

Bridge settings are updated when the config file changes and the proposer is started with --auto_update
The proposer will then try to gather signatures from validators to make the update on chain.

.. image:: images/t_anchor_update.png

If the new anchoring periode reached validator consensus, 
it can then be automatically updated in the bridge contract by the proposer.


.. code-block:: bash

    proposer: mainnet: "Anchoring periode update requested: 7"
    proposer: mainnet: "⌛ tAnchorUpdate success"
    