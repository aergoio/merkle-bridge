Getting started
===============

Download
--------
.. code-block:: bash

    $ git clone git@github.com:aergoio/merkle-bridge.git


Install
-------
Install dependencies

.. code-block:: bash

    $ cd merkle-bridge
    $ virtualenv -p python3 venv
    $ source venv/bin/activate
    $ pip install -r requirements.txt


Optional dev dependencies (lint, testing...)

.. code-block:: bash

    $ pip install -r dev-dependencies.txt


Now you can start using the bridge tools to: 

- create a configuration file with the cli

- deploy a new bridge

- start a proposer

- start a validator

- update bridge settings

- transfer assets through the bridge with the cli
