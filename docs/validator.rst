Validator
=========

A validator will sign any state root from any proposer via the GetAnchorSignature rpc request as long as it is valid.
Therefore a validator must run a full node.
Assets on the sidechain are secure as long as 2/3 of the validators validate both chains and are honnest.
Since signature verification only happens when anchoring (and not when transfering assets), 
the number of validators can be very high as the signature verification cost is necessary only once per anchor.


Configuration
-------------
Configuration file for starting a validator (config.json)

.. code-block:: json
 
    {
        "mainnet": {
            "bridges": {
                "sidechain2": {
                    "addr": "Amgxek6sxArhf3TZsPuqmiokyp6a4dJyex4PnLuGj3XTFSAZ3rh6",
                    "id": "eef35e26c1fe5e3a1235d04affa84a",
                    "t_anchor": 25,
                    "t_final": 5
                }
            },
            "ip": "localhost:7845"
        },
        "sidechain2": {
            "bridges": {
                "mainnet": {
                    "addr": "Amgxek6sxArhf3TZsPuqmiokyp6a4dJyex4PnLuGj3XTFSAZ3rh6",
                    "id": "1631cf317474c11b9e783bd726ab09",
                    "t_anchor": 10,
                    "t_final": 10
                }
            },
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
            "validator": {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "priv_key": "47wwDRMKXH4serxiNQcrtMSxHsGt9qX6wZTt9XNUcABBokLYpUtKuYue1ujmsBLvzy9DcD84i"
            }
        }
    }


Four items need to be registered in the config.json:

- The node ip address of the 'mainnet' and 'sidechain2' blockchains being bridged

- The contract addresses and id variable of bridges on both chains being connected.

- The Aergo Address and ip address of the bridge validators (obviously all validator addresses should be different).
  It is best that validators know the other validators in case of updates

- The address and exported private key (encrypted) used to sign state updates (anchors)



Starting a Validator
--------------------

Modify the script in merkle-bridge/bridge_operator/validator_server.py then: 

.. code-block:: bash

    $ make validator

or

.. code-block:: python

    import json
    from bridge_operator.validator_server import ValidatorServer

    with open("./config.json", "r") as f:
        c = json.load(f)

    validator = ValidatorServer(c, 'mainnet', 'sidechain2')
    validator.run()