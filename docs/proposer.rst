Proposer
========

A proposer connects to all validators and requests them to sign a new anchor 
with the GetAnchorSignature rpc request.
To prevent downtime, anybody can become a proposer and request signatures to validators.
It is the validator's responsibility to only sign correct anchors.
The bridge contracts will not update the state root if the anchoring time is not reached (t_anchor).


Configuration
-------------
Configuration file for starting a proposer (config.json)

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
            "proposer": {
                "addr": "AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU",
                "priv_key": "47sDAWjMFTP7r2JP2BJ29PJRfY13yUTtVvoLjAf8knhH4GryQrpMJoTqscDjed1YPHVZXY4sN"
            }
        }
    }


Four items need to be registered in the config.json:

- The node ip address of the 'mainnet' and 'sidechain2' blockchains being bridged

- The contract addresses and id variable of bridges on both chains being connected.

- The Aergo Address and ip address of the bridge validators (obviously all validator addresses should be different).
  Used to request 2/3 anchor signatures.

- The address and exported private key (encrypted) used to sign state updates (anchors)



Starting a Proposer
--------------------

Modify the script in merkle-bridge/bridge_operator/proposer_client.py then: 

.. code-block:: bash

    $ make proposer

or

.. code-block:: python

    import json
    from bridge_operator.proposer_client import ProposerClient

    with open("./config.json", "r") as f:
        c = json.load(f)

    proposer = ProposerClient(c, 'mainnet', 'sidechain2')
    proposer.run()
