merkle-bridge documentation
===========================

What is the Aergo Merkle bridge ?
---------------------------------
The Aergo Merkle bridge is an efficient and descentralized way of connecting blockchains. 

Release blog article: https://medium.com/aergo/the-aergo-merkle-bridge-explained-d95f7dcec510.

In order to transfer an asset from one blockchain to another blockchain, it should be locked on it’s origin chain and minted on the destination chain. 
At all times the minted assets should be pegged to the locked assets. 

The Aergo Merkle Bridge enables decentralized custody and efficient minting of assets. 

At regular intervals, a proposer publishes the block state root of each chain on the other connected chain's oracle contract. 
The state root is recorded only if it has been signed by 2/3 of validators. 
Validators only sign the general block state root, and the proposer creates a Merkle proof, proving that the bridge contract storage state is included in the general block state.
Users can then independently mint assets on the destination bridge contract by verifying a merkle proof of their locked assets with the anchored storage root.

The proposers do not need to watch and validate user transfers: the benefit of the merkle bridge design comes from the fact that
validators simply make sure that the state roots they sign are correct. Since onchain signature verification is only done once per root anchor,
it is possible to use a large number of validators for best safety and sensorship resistance. 

.. toctree::
   :maxdepth: 2
   :caption: Contents

   getting_started
   cli_operation

   proposer
   validator
   contracts
   config
   wallet

.. toctree::
   :maxdepth: 2
   :caption: References:

   aergo_operator
   aergo_wallet
   aergo_cli



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
