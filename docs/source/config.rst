Configuration file
=====================

The config.json file is used by bridge operators, the wallet and the cli to store information about
node connections, validator connections, bridge parameters, assets and private keys.

It can be created and updated manually of with the help of the cli.

.. code-block:: js

    {
        "networks": { // list of registered networks
            "mainnet": {  // name of blockchain network
                "bridges": {  // bridge contracts to other networks
                    "sidechain2": {  // name of the network being connected
                        "addr": "AmgEZebmD4BcV4dhKq6h2HcJS2E8vvy5CEYPyrTvuohjQMiJqMC4",  // bridge contract (on mainnet) address to sidechain
                        "oracle": "AmgQdbUqDuoX5krsmvSEHc9X3apBuXyJTQ4mimfWzejEsYScTo3f", // oracle controling bridge contract 'addr'
                        "t_anchor": 25,  // anchoring periode of sidechain to mainnet 
                        "t_final": 5  // minimum finality time of sidechain
                    }
                },
                "ip": "localhost:7845",  // ip of a mainnet node for herapy
                "tokens": {  // tokens issued on this network
                    "token1": {  // name of token issued on mainnet
                        "addr": "AmghHtk2gpcpMa6bj1v59qCBfNmKZTi8qDGeuMNg5meJuXGTa2Y1",  // address of token issued on mainnet
                        "pegs": {  // other networks where this token exists (pegged)
                            "sidechain2": "AmgssNKd5xXoCguDUnF9Bzhh78W5arwnMtTgDvPZxaAViGDCWa3m"   // token contract of the asset pegged on another chain
                        }
                    }
                }
            },
            "sidechain2": {  // name of blockchain network
                "bridges": {  // bridge contracts to other networks
                    "mainnet": {  // name of the network being connected
                        "addr": "Amho9dBsJZdbqC1nG4Vztgy7HWfkc6mxiRKjxMUrjPx6kgszdrsa",  // bridge contract (on sidechain) address to mainnet
                        "oracle": "AmgQdbUqDuoX5krsmvSEHc9X3apBuXyJTQ4mimfWzejEsYScTo3f", // oracle controling bridge contract 'addr'
                        "id": "3e688cb882552b4f7d9032e0ae55d9",  // bridge id used to prevent bridge update replay
                        "t_anchor": 10,  // anchoring periode of mainnet to sidechain2 
                        "t_final": 10  // minimum finality time of mainnet
                    }
                },
                "ip": "localhost:8845",  // ip of a sidechain2 node for herapy
                "tokens": {}  // tokens issued on this network
                }
            }
        },
        "validators": [  // array of validators that can update the bridge contracts (order is important)
            {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",  // address of the validator's signing private key
                "ip": "localhost:9841"  // ip address of the validator server signing anchors
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
        "wallet": {  // named accounts
            "broadcaster": {  // name of account
                "addr": "AmMQNBFXuSqiN97rv2m1NoxWu7D2UKAojKCpWqrLmZh676GgfRGG",  // address matching the private key
                "keystore": "keystore/AmMQNBFXuSqiN97rv2m1NoxWu7D2UKAojKCpWqrLmZh676GgfRGG__2020-01-20T04:13:16__keystore.json"  // path to keystore file
            },
            "default": {
                "addr": "AmNPWDJMjU4g98Scm4AikW8JwQMGwWMztM7Qy8ggxNTkhgZMJHFp",
                "keystore": "keystore/AmNPWDJMjU4g98Scm4AikW8JwQMGwWMztM7Qy8ggxNTkhgZMJHFp__2020-01-20T04:13:06__keystore.json"
            },
        }
    }