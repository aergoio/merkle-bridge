Broadcaster
===========

A broadcaster executes pre-signed token transfers and collects a fee in tokens.
It can execute simple transfers and bridge transfers with lock/mint and burn/unlock. 
The broadcaster verifies the signed transfer is correct before executing the transaction.
The broadcaster server operates only between 2 chains.

Configuration
-------------
Configuration file for starting a broadcaster (config.json)

.. code-block:: json
 
    {
        "broadcasters": {
            "mainnet": {
                "ip": "localhost:9850",
                "sidechain2": {
                    "ip": "localhost:9850"
                }
            },
            "sidechain2": {
                "ip": "localhost:9850"
            }
        },
        "mainnet": {
            "bridges": {
                "sidechain2": {
                    "addr": "Amgxek6sxArhf3TZsPuqmiokyp6a4dJyex4PnLuGj3XTFSAZ3rh6",
                    "id": "eef35e26c1fe5e3a1235d04affa84a",
                    "t_anchor": 25,
                    "t_final": 5
                }
            },
            "ip": "localhost:7845",
            "tokens": {
                "my_token": {
                    "addr": "AmgpYGMMPEnb7ukcJkhpGCGJXwqEq2MgpneN47hHrbBS7C3AjDke",
                    "pegs": {
                        "sidechain2": "AmhiUx2hZ9phVDMZoBShEWD2sCFXPJ5BZpagNC8WfssPuZg7wzZS"
                    }
                }
            }
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
            "ip": "localhost:8845",
            "tokens": {}
        },
        "wallet": {
            "broadcaster": {
                "addr": "AmPiFGxLvETrs13QYrHUiYoFqAqqWv7TKYXG21zC8TJfJTDHc7HJ",
                "priv_key": "47T5iXRL4M9mhCZqzxzbWUxhwnE7oDvreBkJuNRADL2DppJDroz1TcEiJF4p9qh6X6Z2ynEMo"
            }
        }
    }


Five items need to be registered in the config.json:

- The node ip address of the 'mainnet' and 'sidechain2' blockchains being bridged
- The address of bridge contracts to other blockchains
- The ip of broadcaster services 
- The address and exported private key (encrypted) used to execute transactions
- Tokens supported by the broadcaster

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