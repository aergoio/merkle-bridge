Bridge Smart-Contracts
======================

A bridge contract is deployed on each blockchain that is being connected.
It's job is to record state roots, lock, mint, burn and unlock assets.

Configuration
-------------
Configuration file for deploying the bridge (config.json)

.. code-block:: json
 
    {
        "mainnet": {
            "bridges": {},
            "ip": "localhost:7845"
        },
        "sidechain2": {
            "bridges": {},
            "ip": "localhost:8845"
        },
        "validators": [
            {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "ip": "localhost:9841"
            },
            {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "ip": "localhost:9842"
            },
            {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "ip": "localhost:9843"
            }
        ],
        "wallet": {
            "proposer": {
                "addr": "AmPiFGxLvETrs13QYrHUiYoFqAqqWv7TKYXG21zC8TJfJTDHc7HJ",
                "priv_key": "47T5iXRL4M9mhCZqzxzbWUxhwnE7oDvreBkJuNRADL2DppJDroz1TcEiJF4p9qh6X6Z2ynEMo"
            },
            "default": {
                "addr": "AmNMFbiVsqy6vg4njsTjgy7bKPFHFYhLV4rzQyrENUS9AM1e3tw5",
                "priv_key": "47CLj29W96rS9SsizUz4pueeuTT2GcSpkoAsvVC3USLzQ5kKTWKmz1WLKnqor2ET7hPd73TC9"
            }
        }
    }


Three items need to be registered in the config.json:

- The node ip address of the 'mainnet' and 'sidechain2' blockchains being bridged

- The Aergo Address and ip address of the bridge validators (obviously all validator addresses should be different)

- The address and exported private key (encrypted) used to sign the deploy transaction

Deploying the bridge
--------------------

To deploy the bridge, you can modify the script in merkle-bridge/bridge_operator/bridge_deployer.py 
then:

.. code-block:: bash

    $ cd path/to/merkle-bridge
    $ make deploy_bridge


Bridge settings
---------------

- Anchoring periode of each blockchain

- Minimum finality time of each blockchain

- Set of validators (same for both sides of the bridge)

Updating settings
-----------------

Updating settings (anchor periode, finality or validators) is done while the bridge is stoped  
and should not occure regularly. 
The BridgeSettingsManager class in merkle-bridge/bridge_operator/bridge_settings.py 
provides the necessary tools.

Process for updating validator set : stop the validators, agree on a new set of validators, gather 2/3 or signatures with
the correct update nonce, execute the tx to register the new validators.

Validator i signs a new validator set:

.. code-block:: python

    with open("./path/to/config.json", "r") as f:
        config_data = json.load(f)

    new_validators = ["AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ"]

    manager = BridgeSettingsManager(config_data)
    sig1_1, sig2_1 = manager.sign_new_validators('mainnet', 'sidechain2',
                                                 new_validators,
                                                 privkey_name='default')

A proposer that gathered 2/3 signatures can then update the bridge contracts :

.. code-block:: python

    with open("./path/to/config.json", "r") as f:
        config_data = json.load(f)

    new_validators = ["AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                      "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ"]

    manager = BridgeSettingsManager(config_data)

    manager.update_validators(new_validators,
                              [1, 2],
                              [sig1_1, sig1_2], 
                              [sig2_1, sig2_2],
                              'mainnet', 'sidechain2',
                              privkey_name='default')

Checking current bridge settings:

.. code-block:: python

    with open("./path/to/config.json", "r") as f:
        config_data = json.load(f)

    manager = BridgeSettingsManager(config_data)
    validators = manager.get_validators('mainnet', 'sidechain2')
    t_anchor = manager.get_t_anchor('mainnet', 'sidechain2')
    t_final = manager.get_t_final('mainnet', 'sidechain2')