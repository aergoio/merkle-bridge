Broadcaster
===========

Deprecation WARNING : broadcaster functionality will be removed with next release.

A broadcaster executes pre-signed token transfers and collects a fee in tokens.
It can execute simple transfers and bridge transfers with lock/mint and burn/unlock. 
The broadcaster verifies the signed transfer is correct before executing the transaction.
The broadcaster server operates only between 2 chains.

Starting a broadcaster
----------------------

Modify the script in merkle-bridge/broadcaster/broadcaster_server.py then: 

.. code-block:: bash

    $ make broadcaster


or

.. code-block:: python

    import json
    from broadcaster.broadcaster_server import BroadcasterServer

    with open("./config.json", "r") as f:
        config_data = json.load(f)
    broadcaster = BroadcasterServer("./config.json", 'mainnet', 'sidechain2')
    broadcaster.run()