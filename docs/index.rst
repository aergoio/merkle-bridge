merkle-bridge documentation
===========================

What is the Aergo Merkle bridge ?
---------------------------------
The Aergo Merkle bridge is an efficient and descentralized way of connecting blockchains. 

Release blog article: https://medium.com/aergo/the-aergo-merkle-bridge-explained-d95f7dcec510.

In order to transfer an asset to another chain, it should be locked on it's origin chain and minted on the destination chain.
At all times the minted assets should be pegged to the locked assets.
The Aergo Merkle Bridge enables decentralized locking and efficient minting of assets.
The bridge is composed of onchain smart-contracts, proposers, validators and of course users making transfers.
At regular intervals, a proposer publishes the state root of the bridge contract on the connected chain.
The state root is recorded only if it has been signed by 2/3 of validators.
Users can then independently mint assets on the destination bridge contract by verifying a merkle proof of their locked assets.
The locked assets can only be unlocked with a proof of burn of minted assets. 

.. toctree::
   :maxdepth: 2
   :caption: Contents

   contracts
   validator
   proposer
   wallet
   broadcaster



Indices and tables
==================

* :ref:`search`
