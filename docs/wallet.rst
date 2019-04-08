Python wallet
=============

The Python wallet can be used as a python command line tool for making simple transfers, 
bridge transfers, quering balances ...
The merkle-bridge/wallet repository can also be used as a module for other applications 
as the tools are separate and don't need config.json to be used. 

Configuration
-------------
Configuration file for using the wallet (config.json)

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
                    "addr": "AmgkVksed7GcPTnMNKs1pojtEXio2nd58cXMMwfe7CY6j7bKz7jU"
                }
            },
            "ip": "localhost:7845",
            "tokens": {
                "aergo": {
                    "addr": "aergo",
                    "pegs": {}
                },
            }
        },
        "sidechain2": {
            "bridges": {
                "mainnet": {
                    "addr": "Amg4xbhuQcj73eHvQtV4U26yyRe9TiWrKX8qGs5SWXG7N4yAcLyB"
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
        "wallet": {
            "default": {
                "addr": "AmNMFbiVsqy6vg4njsTjgy7bKPFHFYhLV4rzQyrENUS9AM1e3tw5",
                "priv_key": "47CLj29W96rS9SsizUz4pueeuTT2GcSpkoAsvVC3USLzQ5kKTWKmz1WLKnqor2ET7hPd73TC9"
            }
        }
    }


Three items need to be registered in the config.json:

- The node ip address of the 'mainnet' and 'sidechain2' blockchains being bridged
- The address of bridge contracts to other blockchains
- The ip of broadcaster services (for paying fees in tokens instead of AER)


Create / Register a new account
----------------------

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    # create a new account (new private key), 
    # you will be requested to create a password 
    # (DO NOT LOSE IT, it is the only way to decrypt your private key)
    wallet.create_account("default")

    # if you already have an exported private key (created by aergocli for example)
    wallet.register_account('default', "exported_private_key", addr="Address_of_private_key")


Balance query
-------------

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    # get Aer balance of the default account on 'mainnet'
    balance, _ = wallet.get_balance('aergo', 'mainnet')

    # get Aer balance of Aer minted on 'sidechain2'
    balance, _ = wallet.get_balance('aergo', 'sidechain2',
                                    asset_origin_chain='mainnet')

Deploy a test token
-------------------

.. code-block:: python

    from wallet.wallet import Wallet

    # load the compiled bytecode
    with open("./contracts/token_bytecode.txt", "r") as f:
        bytecode = f.read()[:-1]

    # create a wallet
    wallet = Wallet("./config.json")

    total_supply = 500*10**18
    token_name = "my_token"
    # deploy the token and stored the address in config.json
    wallet.deploy_token(bytecode, token_name, total_supply, "mainnet")


Register an already deployed token
----------------------------------
This can be done by editing config.json directly.

.. code-block:: json

    {
        "tokens": {
            "aergo": {
                "addr": "aergo",
                "pegs": {
                    "sidechain2": "AmhtCQgBeHFVMTDNGup8UFZTgr3Soj2zMeGhEaRs5UD6SzyUhqxm"
                }
            },
            "my_token": {
                "addr": "AmgY8WARSNfjgCnFhFJBv145wkHJRTC7YR5MeJGAMvKzVD9kKeFz",
                "pegs": {
                    "sidechain2": "AmheFWQf5decPrKZE1dnjh1EFwDq7qqAmobPbrUt4XeNK9QNCyxK"
                }
            }
        }
    }

or with the wallet:

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    " Register a 'mainnet' token and it's pegged self on 'sidechain2'
    wallet.register_asset("my_token", "mainnet", "Address on mainnet",
                          pegged_chain_name="sidechain2",
                          addr_on_pegged_chain="Address on sidechain2")

Simple Transfers
---------------- 

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    # simple asset transfer on 'mainnet'
    wallet.transfer(2*10**18, to_address, asset_name="my_token", network_name="mainnet")

    # simple asset transfer of 'mainnet' assets pegged on 'sidechain'
    wallet.transfer(2*10**18, to_address, asset_name="my_token", network_name="sidechain",
                    asset_origin_chain="mainnet")


Bridge Transfers
----------------

The transfer_to_sidechain method performs the following:

- lock assets in the bridge contract
- wait for the next anchor on sidechain
- create a merkle proof of lock in the anchored state
- mint the asset on the sidechain with the merkle proof

The transfer_from_sidechain method performs the following:

- brun assets in the bridge contract
- wait for the next anchor on mainnet
- create a merkle proof of burn in the anchored state
- unlock the asset on the mainnet with the merkle proof


.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    amount = 1*10**18
    asset = 'aergo'
    # transfer aergo from 'mainnet' to 'sidechain2'
    wallet.transfer_to_sidechain('mainnet',
                                 'sidechain2',
                                 asset,
                                 amount)

    # transfer minted aergo from sidechain2 mainnet
    wallet.transfer_from_sidechain('sidechain2',
                                   'mainnet',
                                   asset,
                                   amount)


It is also possible to perform the lock/burn and mint/unlock operations individually.

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    amount = 1*10**18
    asset = 'aergo'
    # lock asset in the bridge contract to 'sidechain2'
    lock_height, tx_hash = wallet.initiate_transfer_lock('mainnet', 'sidechain2',
                                                         asset, amount)
    # lock more assets in the bridge contract to 'sidechain2'
    lock_height, tx_hash = wallet.initiate_transfer_lock('mainnet', 'sidechain2',
                                                         asset, amount)

    # get the amount of assets locked but not yet minted on 'sidechain2'
    pending_mint = wallet.get_minteable_balance(
        'mainnet', 'sidechain2', asset, pending=True
    )

    # mint the total balance of two previous locked amounts
    pegged_address, tx_hash = wallet.finalize_transfer_mint(
        'mainnet', 'sidechain2', asset, lock_height=lock_height
    )


    # Similarly, 
    # wallet.initiate_transfer_burn()
    # wallet.get_unlockeable_balance()
    # wallet.finalize_transfer_unlock() 
    # can be used to burn and unlock minted assets from a sidechain.


Using a Broadcaster
-------------------

When using a broadcaster to transfer tokens, the user pre-signs the nonce of a standard token
transfer with a fee in tokens for the broadcaster.
The broadcaster collects the token fee for executing the transactions, and the user doesn't
need to hold Aer in his wallet to make transfers.
The broadcaster's ip address should be registered in the wallet's config.json

.. code-block:: python

    from wallet.wallet import Wallet

    # create a wallet
    wallet = Wallet("./config.json")

    amount = 100*10**18
    fee = 2*10**18
    # the name of the asset should be same as the name registered in the standard token's 
    # Name state variable otherwise the broadcaster will say asset is not suported
    asset = 'my_token'

    # simple broadcasted transfer on 'mainnet'
    wallet.d_transfer(amount, fee, to_address, asset, 'mainnet')

    # simple broadcasted transfer of a 'mainnet' asset pegged on 'sidechain2'
    wallet.d_transfer(amount, fee, to_address, asset, 'sidechain2',
                      asset_origin_chain='mainnet')

    # Transfer asset from 'mainnet' to 'sidechain2'
    # The broadcaster collects the asset fee on 'mainnet' and mints on 'sidechain2'
    # Note : nothing actually forces the broadcaster to mint on sidechain.
    # If the broadcaster is not nice and doesn't mint, users can use another broadcaster next time
    wallet.d_transfer_to_sidechain('mainnet', 'sidechain2', asset, amount, fee)

    # Transfer asset from 'sidechain2' to 'mainnet'
    wallet.d_transfer_from_sidechain('sidechain2', 'mainnet', asset, amount, fee)


Wallet utils
------------

If you wish to use the wallet as a module for other applications, the following tools are available:

- wallet_utils.py
- transfer_to_sidechain.py
- transfer_from_sidechain.py
- token_deployer.py

You will need to connect your own herapy instances to nodes and load your private key in herapy.
