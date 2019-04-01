Configuration example

The config.json file is used by bridge operators, broadcasters and the python wallet to
stores information about asset addresses, bridge addresses, validators, network nodes etc...

.. code-block:: json

    {
        "broadcasters": {
            "mainnet": {
                "ip": "localhost:9850", // ip of the mainnet broadcaster service
                "sidechain2": {
                    "ip": "localhost:9850" # ip of the mainnet-sidechain2 broadcaster service
                }
            },
            "sidechain2": {
                "ip": "localhost:9850"  # ip of the sidechain2 broadcaster
            }
        },
        "mainnet": {
            "bridges": {
                "": {
                    "addr": "bridge address on mainnet",
                    "id": "bridge ContractID variable",
                    "t_anchor": "t_anchor of sidechain on mainnet",
                    "t_final": "t_final of sidechain"
                },
                "sidechain2": {
                    "addr": "AmgEZebmD4BcV4dhKq6h2HcJS2E8vvy5CEYPyrTvuohjQMiJqMC4",
                    "t_anchor": 25,
                    "t_final": 5
                }
            },
            "ip": "localhost:7845",
            "tokens": {
                "aergo": {
                    "addr": "aergo",
                    "pegs": {
                        "sidechain2": "AmhaiDcJaVVmaUpUUbctuARKLZodJgXMjiiPz6hAgRg7nwnqKT79"
                    }
                },
                "tok": {
                    "addr": "Address",
                    "pegs": {
                        "side": "sideaddr"
                    }
                },
                "token1": {
                    "addr": "AmghHtk2gpcpMa6bj1v59qCBfNmKZTi8qDGeuMNg5meJuXGTa2Y1",
                    "pegs": {
                        "sidechain2": "AmgssNKd5xXoCguDUnF9Bzhh78W5arwnMtTgDvPZxaAViGDCWa3m"
                    }
                }
            }
        },
        "sidechain2": {
            "bridges": {
                "": {
                    "addr": "bridge address on sidechain",
                    "id": "bridge ContractID variable",
                    "t_anchor": "t_anchor of mainnet on sidechain",
                    "t_final": "t_final of mainnet"
                },
                "mainnet": {
                    "addr": "Amho9dBsJZdbqC1nG4Vztgy7HWfkc6mxiRKjxMUrjPx6kgszdrsa",
                    "t_anchor": 10,
                    "t_final": 10
                }
            },
            "ip": "localhost:8845",
            "tokens": {
                "aergo": {
                    "addr": "aergo",
                    "pegs": {}
                }
            }
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
            "broadcaster": {
                "addr": "AmPiFGxLvETrs13QYrHUiYoFqAqqWv7TKYXG21zC8TJfJTDHc7HJ",
                "priv_key": "47T5iXRL4M9mhCZqzxzbWUxhwnE7oDvreBkJuNRADL2DppJDroz1TcEiJF4p9qh6X6Z2ynEMo"
            },
            "default": {
                "addr": "AmNMFbiVsqy6vg4njsTjgy7bKPFHFYhLV4rzQyrENUS9AM1e3tw5",
                "priv_key": "47CLj29W96rS9SsizUz4pueeuTT2GcSpkoAsvVC3USLzQ5kKTWKmz1WLKnqor2ET7hPd73TC9"
            },
            "default2": {
                "addr": "AmNyNPEqeXPfdHeECMNhsH1QcnZsqCtDAudjgFyG5qpasN6tyLPE",
                "priv_key": "47PZc88CguT8Vm5MJXR7FAy9ewDmnHhyU6w8r2GgRpciz55wUieQVacPaVgUZP7yZGMYEs9BD"
            },
            "proposer": {
                "addr": "AmPxVdu993eosN3UjnPDdN3wb7TNbHeiHDvn2dvZUcH8KXDK3RLU",
                "priv_key": "47sDAWjMFTP7r2JP2BJ29PJRfY13yUTtVvoLjAf8knhH4GryQrpMJoTqscDjed1YPHVZXY4sN"
            },
            "receiver": {
                "addr": "AmPf349iHWd6kQGU45BxFzFCzEDu75Y3FqFPd4WBMteFq4mtDuZd",
                "priv_key": "47HzJAwuTV1akJPtsBWm4saJaQAgKgq1qSeeKfaFHnMxhjPM5ipPY8EZ3gDVRQ4oLizx1qhwh"
            },
            "test": {
                "addr": "AmM6Db1e8PbDAbCfKgD4s3SfM8xJfkTvEaLZK4exVuWFnYL34S93",
                "priv_key": "47hxG12EStVwAG6ww5DYRKaKqWB47JhmRwK6kTW9hXbN79Chh2cQAwx4qYxmYvnD3Ys9f5c1x"
            },
            "validator": {
                "addr": "AmNLjcxUDmxeGZL7F8bqyaGt3zqog5HAoJmFBEZAx1RvfTKLSBsQ",
                "priv_key": "47wwDRMKXH4serxiNQcrtMSxHsGt9qX6wZTt9XNUcABBokLYpUtKuYue1ujmsBLvzy9DcD84i"
            }
        }
    }