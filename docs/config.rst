Configuration example
=====================

The config.json file is used by bridge operators, broadcasters and the python wallet to
store information about asset addresses, bridge addresses, validators, network nodes etc...

This is what a configuration file might look like with 2 bridged networks and tokens sent from one to the other:

.. code-block:: js

    {
        "broadcasters": {  // named broadcasters
            "mainnet": {  // name of broadcaster on mainnet
                "ip": "localhost:9850",  // ip of the mainnet broadcaster service
                "sidechain2": {  // name of mainnet-sidechain2 broadcaster
                    "ip": "localhost:9850"  // ip of the mainnet-sidechain2 broadcaster service
                }
            },
            "sidechain2": {
                "ip": "localhost:9850"  // ip of the sidechain2 broadcaster
            }
        },
        "mainnet": {  // name of blockchain network
            "bridges": {  // bridge contracts to other networks
                "sidechain2": {  // name of the network being connected
                    "addr": "AmgEZebmD4BcV4dhKq6h2HcJS2E8vvy5CEYPyrTvuohjQMiJqMC4",  // bridge contract (on mainnet) address to sidechain
                    "id": "4ad2de8bc41f0cdf75473bb470ced0",  // bridge id used to prevent bridge update replay
                    "t_anchor": 25,  // anchoring periode of sidechain to mainnet 
                    "t_final": 5  // minimum finality time of sidechain
                }
            },
            "ip": "localhost:7845",  // ip of a mainnet node for herapy
            "tokens": {  // tokens issued on this network
                "aergo": {  // name of token issued on mainnet
                    "addr": "aergo",  // "aergo" means native chain token
                    "pegs": {  // other networks where this token exists (pegged)
                        "sidechain2": "AmhaiDcJaVVmaUpUUbctuARKLZodJgXMjiiPz6hAgRg7nwnqKT79"  // token contract of the asset on another chain
                    }
                },
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
                    "id": "3e688cb882552b4f7d9032e0ae55d9",  // bridge id used to prevent bridge update replay
                    "t_anchor": 10,  // anchoring periode of mainnet to sidechain2 
                    "t_final": 10  // minimum finality time of mainnet
                }
            },
            "ip": "localhost:8845",  // ip of a sidechain2 node for herapy
            "tokens": {  // tokens issued on this network
                "aergo": {  // name of token issued on mainnet
                    "addr": "aergo",  // "aergo" means native chain token
                    "pegs": {}  // other networks where this token exists (pegged)
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
                "addr": "AmPiFGxLvETrs13QYrHUiYoFqAqqWv7TKYXG21zC8TJfJTDHc7HJ",  // address matching the private key
                "priv_key": "47T5iXRL4M9mhCZqzxzbWUxhwnE7oDvreBkJuNRADL2DppJDroz1TcEiJF4p9qh6X6Z2ynEMo"  // exported (encrypted) private key
            },
            "default": {
                "addr": "AmNMFbiVsqy6vg4njsTjgy7bKPFHFYhLV4rzQyrENUS9AM1e3tw5",
                "priv_key": "47CLj29W96rS9SsizUz4pueeuTT2GcSpkoAsvVC3USLzQ5kKTWKmz1WLKnqor2ET7hPd73TC9"
            },
            "proposer": {
                "addr": "AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU",
                "priv_key": "47sDAWjMFTP7r2JP2BJ29PJRfY13yUTtVvoLjAf8knhH4GryQrpMJoTqscDjed1YPHVZXY4sN"
            },
            "validator": {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "priv_key": "47wwDRMKXH4serxiNQcrtMSxHsGt9qX6wZTt9XNUcABBokLYpUtKuYue1ujmsBLvzy9DcD84i"
            }
        }
    }