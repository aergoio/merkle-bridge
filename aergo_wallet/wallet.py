from getpass import getpass
import json

from typing import (
    Union,
    Tuple,
    List,
    Dict,
)

import aergo.herapy as herapy
from aergo.herapy.errors.general_exception import (
    GeneralException,
)

from aergo_wallet.transfer_to_sidechain import (
    lock,
    build_lock_proof,
    mint,
)
from aergo_wallet.transfer_from_sidechain import (
    burn,
    build_burn_proof,
    unlock,
)
from aergo_wallet.exceptions import (
    InvalidArgumentsError,
    InsufficientBalanceError,
)
from aergo_wallet.wallet_utils import (
    get_balance,
    transfer,
    bridge_withdrawable_balance,
    wait_finalization
)
from aergo_wallet.token_deployer import (
    deploy_token,
)
import logging

logger = logging.getLogger(__name__)


class AergoWallet:
    """ A wallet loads it's private key from config.json and
    implements the functionality to transfer tokens to sidechains
    """

    def __init__(
        self,
        config_file_path: str,
        config_data: Dict = None,
    ) -> None:
        if config_data is None:
            with open(config_file_path, "r") as f:
                config_data = json.load(f)
        self._config_data = config_data
        self._config_path = config_file_path
        self.gas_price = 0

    def config_data(
        self,
        *json_path: Union[str, int],
        value: Union[str, int, List, Dict] = None
    ):
        """ Get the value in nested dictionary at the end of
        json path if value is None, or set value at the end of
        the path.
        """
        config_dict = self._config_data
        for key in json_path[:-1]:
            config_dict = config_dict[key]
        if value is not None:
            config_dict[json_path[-1]] = value
        return config_dict[json_path[-1]]

    def save_config(self, path: str = None) -> None:
        if path is None:
            path = self._config_path
        with open(path, "w") as f:
            json.dump(self._config_data, f, indent=4, sort_keys=True)

    def _load_priv_key(
        self,
        account_name: str = 'default',
        password: str = None
    ) -> str:
        """ Load and maybe prompt user password to decrypt priv_key."""
        exported_privkey = self.config_data('wallet', account_name, 'priv_key')
        if password is None:
            password = getpass("Decrypt exported private key '{}'\nPassword: "
                               .format(account_name))
        aergo = herapy.Aergo()
        account = aergo.import_account(exported_privkey, password,
                                       skip_state=True, skip_self=True)
        priv_key = str(account.private_key)
        return priv_key

    def create_account(
        self,
        account_name: str,
        password: str = None
    ) -> str:
        if password is None:
            while True:
                password = getpass("Create a password for '{}': "
                                   .format(account_name))
                confirm = getpass("Confirm password: ")
                if password == confirm:
                    break
                logger.info("Passwords don't match, try again")
        aergo = herapy.Aergo()
        aergo.new_account(skip_state=True)
        exported_privkey = aergo.export_account(password)
        addr = str(aergo.account.address)
        return self.register_account(account_name, exported_privkey, addr=addr)

    def get_wallet_address(self, account_name: str = 'default') -> str:
        addr = self.config_data('wallet', account_name, 'addr')
        return addr

    def register_account(
        self,
        account_name: str,
        exported_privkey: str,
        password: str = None,
        addr: str = None
    ) -> str:
        """Register and exported account to config.json"""
        try:
            self.config_data('wallet', account_name)
        except KeyError:
            # if KeyError then account doesn't already exists
            if addr is None:
                aergo = herapy.Aergo()
                account = aergo.import_account(exported_privkey, password,
                                               skip_state=True, skip_self=True)
                addr = str(account.address)
            self.config_data('wallet', account_name, value={})
            self.config_data('wallet', account_name, 'addr', value=addr)
            self.config_data(
                'wallet', account_name, 'priv_key', value=exported_privkey)
            self.save_config()
            return addr
        error = "Error: account name '{}' already exists".format(account_name)
        raise InvalidArgumentsError(error)

    def register_asset(
        self,
        asset_name: str,
        origin_chain_name: str,
        addr_on_origin_chain: str,
        pegged_chain_name: str = None,
        addr_on_pegged_chain: str = None
    ) -> None:
        """ Register an existing asset to config.json"""
        self.config_data(
            'networks', origin_chain_name, 'tokens', asset_name, value={})
        self.config_data(
            'networks', origin_chain_name, 'tokens', asset_name, 'addr',
            value=addr_on_origin_chain)
        self.config_data(
            'networks', origin_chain_name, 'tokens', asset_name, 'pegs',
            value={})
        if pegged_chain_name is not None and addr_on_pegged_chain is not None:
            self.config_data(
                'networks', origin_chain_name, 'tokens', asset_name, 'pegs',
                pegged_chain_name, value=addr_on_pegged_chain)
        self.save_config()

    def _connect_aergo(self, network_name: str) -> herapy.Aergo:
        aergo = herapy.Aergo()
        aergo.connect(self.config_data('networks', network_name, 'ip'))
        return aergo

    def get_aergo(
        self,
        network_name: str,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        skip_state: bool = False
    ) -> herapy.Aergo:
        """ Return aergo provider with new account created with
        priv_key
        """
        if network_name is None:
            raise InvalidArgumentsError("Provide network_name")
        exported_privkey = self.config_data('wallet', privkey_name, 'priv_key')
        aergo = self._connect_aergo(network_name)
        if privkey_pwd is None:
            logger.info("Decrypt exported private key '%s'", privkey_name)
            while True:
                try:
                    privkey_pwd = getpass("Password: ")
                    aergo.import_account(exported_privkey, privkey_pwd,
                                         skip_state=skip_state)
                except GeneralException:
                    logger.info("Wrong password, try again")
                    continue
                break
        else:
            aergo.import_account(exported_privkey, privkey_pwd,
                                 skip_state=skip_state)
        return aergo

    def get_asset_address(
        self,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None
    ) -> str:
        """ Get the address of a time in config_data given it's name"""
        if asset_origin_chain is None:
            # query a token issued on network_name
            asset_addr = self.config_data(
                'networks', network_name, 'tokens', asset_name, 'addr')
        else:
            # query a pegged token (from asset_origin_chain) balance
            # on network_name sidechain (token or aer)
            asset_addr = self.config_data(
                'networks', asset_origin_chain, 'tokens', asset_name, 'pegs',
                network_name)
        return asset_addr

    def get_balance(
        self,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None,
        account_name: str = 'default',
        account_addr: str = None
    ) -> Tuple[int, str]:
        """ Get account name balance of asset_name on network_name,
        and specify asset_origin_chain for a pegged asset query,
        """
        if account_addr is None:
            account_addr = self.get_wallet_address(account_name)
        aergo = self._connect_aergo(network_name)
        if asset_name == 'aergo':
            asset_addr = 'aergo'
        else:
            asset_addr = self.get_asset_address(asset_name, network_name,
                                                asset_origin_chain)
        balance = get_balance(account_addr, asset_addr, aergo)
        aergo.disconnect()
        return balance, asset_addr

    def get_mintable_balance(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        account_name: str = 'default',
        account_addr: str = None,
    ) -> Tuple[int, int]:
        """ Get the balance that has been locked on one side of the
        bridge and not yet minted on the other side
        Calculates the difference between the total amount deposited and
        total amount withdrawn.
        Set pending to true to include deposits than have not yet been anchored
        """
        if account_addr is None:
            account_addr = self.get_wallet_address(account_name)
        asset_address_origin = self.config_data(
            'networks', from_chain, 'tokens', asset_name, 'addr')
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(
            'networks', to_chain, 'bridges', from_chain, 'addr')
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        withdrawable, pending = bridge_withdrawable_balance(
            account_addr, asset_address_origin, bridge_from, bridge_to,
            aergo_from, aergo_to, "_sv__locks-", "_sv__mints-"
        )
        aergo_from.disconnect()
        aergo_to.disconnect()
        return withdrawable, pending

    def get_unlockable_balance(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        account_name: str = 'default',
        account_addr: str = None,
    ) -> Tuple[int, int]:
        """ Get the balance that has been burnt on one side of the
        bridge and not yet unlocked on the other side
        Calculates the difference between the total amount deposited and
        total amount withdrawn.
        Set pending to true to include deposits than have not yet been anchored
        """
        if account_addr is None:
            account_addr = self.get_wallet_address(account_name)
        asset_address_origin = self.config_data(
            'networks', to_chain, 'tokens', asset_name, 'addr')
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(
            'networks', to_chain, 'bridges', from_chain, 'addr')
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        withdrawable, pending = bridge_withdrawable_balance(
            account_addr, asset_address_origin, bridge_from, bridge_to,
            aergo_from, aergo_to, "_sv__burns-", "_sv__unlocks-"
        )
        aergo_from.disconnect()
        aergo_to.disconnect()
        return withdrawable, pending

    def get_bridge_tempo(
        self,
        from_chain: str,
        to_chain: str,
        aergo: herapy.Aergo = None,
        bridge_address: str = None,
        sync: bool = False
    ) -> Tuple[int, int]:
        """ Return the anchoring periode of from_chain onto to_chain
        and minimum finality time of from_chain. This information is
        queried from bridge_to.
        """
        if not sync:
            t_anchor = self.config_data(
                'networks', to_chain, 'bridges', from_chain, "t_anchor")
            t_final = self.config_data(
                'networks', to_chain, 'bridges', from_chain, "t_final")
            return t_anchor, t_final
        logger.info(
            "getting latest t_anchor and t_final from bridge contract...")
        if aergo is None:
            aergo = self._connect_aergo(to_chain)
        if bridge_address is None:
            bridge_address = self.config_data(
                'networks', to_chain, 'bridges', from_chain, 'addr')
        # Get bridge information
        bridge_info = aergo.query_sc_state(bridge_address,
                                           ["_sv__tAnchor",
                                            "_sv__tFinal",
                                            ])
        if not bridge_info.account.state_proof.inclusion:
            raise InvalidArgumentsError(
                "Contract doesnt exist in state, check contract deployed and "
                "chain synced {}".format(bridge_info))
        if not bridge_info.var_proofs[0].inclusion:
            raise InvalidArgumentsError("Cannot query T_anchor",
                                        bridge_info)
        if not bridge_info.var_proofs[1].inclusion:
            raise InvalidArgumentsError("Cannot query T_final",
                                        bridge_info)
        t_anchor, t_final = [int(item.value)
                             for item in bridge_info.var_proofs]
        aergo.disconnect()
        self.config_data(
            'networks', to_chain, 'bridges', from_chain, "t_anchor",
            value=t_anchor)
        self.config_data(
            'networks', to_chain, 'bridges', from_chain, "t_final",
            value=t_final)
        self.save_config()
        return t_anchor, t_final

    def wait_finalization(
        self,
        network_name: str
    ) -> None:
        aergo = self._connect_aergo(network_name)
        wait_finalization(aergo)

    def transfer(
        self,
        value: int,
        to: str,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
    ) -> str:
        """ Transfer aer or tokens on network_name and specify
        asset_origin_chain for transfers of pegged assets.
        """
        aergo = self.get_aergo(network_name, privkey_name, privkey_pwd,
                               skip_state=True)
        sender = str(aergo.account.address)
        balance, asset_addr = self.get_balance(
            asset_name, network_name, asset_origin_chain, account_addr=sender
        )
        if asset_name == 'aergo':
            gas_limit = 300000
            if balance < value + gas_limit*self.gas_price:
                raise InsufficientBalanceError("not enough balance")
        else:
            gas_limit = 300000
            if balance < value:
                raise InsufficientBalanceError("not enough token balance")
            aer_balance, _ = self.get_balance(
                'aergo', network_name, account_addr=sender
            )
            if aer_balance < gas_limit*self.gas_price:
                err = "not enough aer balance to pay tx fee"
                raise InsufficientBalanceError(err)

        tx_hash = transfer(value, to, asset_addr, aergo, sender, gas_limit,
                           self.gas_price)
        aergo.disconnect()
        logger.info("Transfer success: %s", tx_hash)
        return tx_hash

    def deploy_token(
        self,
        payload_str: str,
        asset_name: str,
        total_supply: int,
        network_name: str,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> str:
        """ Deploy a new standard token, store the address in
        config_data
        """
        aergo = self.get_aergo(network_name, privkey_name, privkey_pwd)
        if receiver is None:
            receiver = str(aergo.account.address)
        logger.info("  > Sender Address: %s", receiver)

        gas_limit = 0
        sc_address = deploy_token(payload_str, aergo, receiver, total_supply,
                                  gas_limit, self.gas_price)

        logger.info("------ Store address in config.json -----------")
        self.config_data(
            'networks', network_name, 'tokens', asset_name, value={})
        self.config_data(
            'networks', network_name, 'tokens', asset_name, 'addr',
            value=sc_address)
        self.config_data(
            'networks', network_name, 'tokens', asset_name, 'pegs',
            value={})
        self.save_config()
        aergo.disconnect()
        return sc_address

    def transfer_to_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        amount: int,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> None:
        """ Transfer assets from from_chain to to_chain.
        The asset being transfered to the to_chain sidechain
        should be native of from_chain
        """
        if receiver is None:
            receiver = self.get_wallet_address(privkey_name)

        lock_height, _ = self.initiate_transfer_lock(
            from_chain, to_chain, asset_name, amount, receiver, privkey_name,
            privkey_pwd
        )
        mintable, pending = self.get_mintable_balance(
            from_chain, to_chain, asset_name, account_addr=receiver
        )
        logger.info("pending mint: %s", mintable + pending)
        logger.info("waiting finalisation ...")
        self.wait_finalization(from_chain)

        self.finalize_transfer_mint(
            from_chain, to_chain, asset_name, receiver, lock_height,
            privkey_name, privkey_pwd
        )

    def transfer_from_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        amount: int,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
    ) -> None:
        """ Transfer assets from from_chain to to_chain
        The asset being transfered back to the to_chain native chain
        should be a minted asset on the sidechain.
        """
        if receiver is None:
            receiver = self.get_wallet_address(privkey_name)

        burn_height, _ = self.initiate_transfer_burn(
            from_chain, to_chain, asset_name, amount, receiver, privkey_name,
            privkey_pwd
        )
        unlockable, pending = self.get_unlockable_balance(
            from_chain, to_chain, asset_name, account_addr=receiver
        )
        logger.info("pending unlock: %s", unlockable + pending)
        logger.info("waiting finalisation ...")
        self.wait_finalization(from_chain)

        self.finalize_transfer_unlock(
            from_chain, to_chain, asset_name, receiver, burn_height,
            privkey_name, privkey_pwd
        )

    def initiate_transfer_lock(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        amount: int,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> Tuple[int, str]:
        """ Initiate a transfer to a sidechain by locking the asset.
        """
        logger.info(from_chain + ' -> ' + to_chain)
        aergo_from = self.get_aergo(from_chain, privkey_name, privkey_pwd)
        sender = str(aergo_from.account.address)
        if receiver is None:
            receiver = sender
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        asset_address = self.config_data(
            'networks', from_chain, 'tokens', asset_name, 'addr')

        gas_limit = 300000
        balance = get_balance(sender, asset_address, aergo_from)
        if balance < amount:
            raise InsufficientBalanceError("not enough token balance")
        logger.info(
            "\U0001f4b0 %s balance on origin before transfer: %s",
            asset_name, balance/10**18
        )

        aer_balance = get_balance(sender, 'aergo', aergo_from)
        if aer_balance < gas_limit*self.gas_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        lock_height, tx_hash = lock(aergo_from, bridge_from,
                                    receiver, amount, asset_address, gas_limit,
                                    self.gas_price)
        logger.info('\U0001f512 Lock success: %s', tx_hash)

        # remaining balance on origin : aer or asset
        balance = get_balance(sender, asset_address, aergo_from)
        logger.info(
            "\U0001f4b0 remaining %s balance on origin after transfer: %s",
            asset_name, balance/10**18
        )

        aergo_from.disconnect()
        return lock_height, tx_hash

    def finalize_transfer_mint(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        receiver: str = None,
        lock_height: int = 0,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> Tuple[str, str]:
        """
        Finalize a transfer of assets to a sidechain by minting then
        after the lock is final and a new anchor was made.
        NOTE anybody can mint so sender is not necessary.
        The amount to mint is the difference between total deposit and
        already minted amount.
        Bridge tempo is taken from config_data
        """
        logger.info(from_chain + ' -> ' + to_chain)
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self.get_aergo(to_chain, privkey_name, privkey_pwd)
        tx_sender = str(aergo_to.account.address)
        if receiver is None:
            receiver = tx_sender
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(
            'networks', to_chain, 'bridges', from_chain, 'addr')
        asset_address = self.config_data(
            'networks', from_chain, 'tokens', asset_name, 'addr')
        save_pegged_token_address = False
        try:
            token_pegged = self.config_data(
                'networks', from_chain, 'tokens', asset_name, 'pegs', to_chain)
            balance = get_balance(receiver, token_pegged, aergo_to)
            logger.info(
                "\U0001f4b0 %s balance on destination before transfer : %s",
                asset_name, balance/10**18
            )
        except KeyError:
            logger.info("Pegged token unknow by wallet")
            save_pegged_token_address = True

        gas_limit = 300000
        aer_balance = get_balance(tx_sender, 'aergo', aergo_to)
        if aer_balance < gas_limit*self.gas_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      asset_address)
        logger.info("\u2699 Built lock proof")
        token_pegged, tx_hash = mint(
            aergo_to, receiver, lock_proof, asset_address, bridge_to,
            gas_limit, self.gas_price
        )
        logger.info('\u26cf Mint success: %s', tx_hash)

        # new balance on sidechain
        balance = get_balance(receiver, token_pegged, aergo_to)
        logger.info(
            "\U0001f4b0 %s balance on destination after transfer : %s",
            asset_name, balance/10**18
        )

        aergo_from.disconnect()
        aergo_to.disconnect()

        # record mint address in file
        if save_pegged_token_address:
            logger.info("------ Store mint address in config.json -----------")
            self.config_data(
                'networks', from_chain, 'tokens', asset_name, 'pegs', to_chain,
                value=token_pegged)
            self.save_config()
        return token_pegged, tx_hash

    def initiate_transfer_burn(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        amount: int,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
    ) -> Tuple[int, str]:
        """ Initiate a transfer from a sidechain by burning the assets.
        """
        logger.info(from_chain + ' -> ' + to_chain)
        aergo_from = self.get_aergo(from_chain, privkey_name, privkey_pwd)
        sender = str(aergo_from.account.address)
        if receiver is None:
            receiver = sender
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        token_pegged = self.config_data(
            'networks', to_chain, 'tokens', asset_name, 'pegs', from_chain)
        balance = get_balance(sender, token_pegged, aergo_from)
        logger.info(
            "\U0001f4b0 %s balance on sidechain before transfer: %s",
            asset_name, balance/10**18
        )
        if balance < amount:
            raise InsufficientBalanceError("not enough balance")

        gas_limit = 300000
        aer_balance = get_balance(sender, 'aergo', aergo_from)
        if aer_balance < gas_limit*self.gas_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        burn_height, tx_hash = burn(aergo_from, bridge_from, receiver, amount,
                                    token_pegged, gas_limit, self.gas_price)
        logger.info('\U0001f525 Burn success: %s', tx_hash)

        # remaining balance on sidechain
        balance = get_balance(sender, token_pegged, aergo_from)
        logger.info(
            "\U0001f4b0 remaining %s balance on sidechain after transfer: %s",
            asset_name, balance/10**18
        )

        aergo_from.disconnect()

        return burn_height, tx_hash

    def finalize_transfer_unlock(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        receiver: str = None,
        burn_height: int = 0,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> str:
        """
        Finalize a transfer of assets from a sidechain by unlocking then
        after the burn is final and a new anchor was made.
        NOTE anybody can unlock so sender is not necessary.
        The amount to unlock is the difference between total burn and
        already unlocked amount.
        Bridge tempo is taken from config_data
        """
        logger.info(from_chain + ' -> ' + to_chain)
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self.get_aergo(to_chain, privkey_name, privkey_pwd)
        tx_sender = str(aergo_to.account.address)
        if receiver is None:
            receiver = tx_sender
        bridge_to = self.config_data(
            'networks', to_chain, 'bridges', from_chain, 'addr')
        bridge_from = self.config_data(
            'networks', from_chain, 'bridges', to_chain, 'addr')
        asset_address = self.config_data(
            'networks', to_chain, 'tokens', asset_name, 'addr')

        burn_proof = build_burn_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, burn_height,
                                      asset_address)
        logger.info("\u2699 Built burn proof")

        balance = get_balance(receiver, asset_address, aergo_to)
        logger.info(
            "\U0001f4b0 %s balance on destination before transfer: %s",
            asset_name, balance/10**18
        )

        gas_limit = 300000
        aer_balance = get_balance(tx_sender, 'aergo', aergo_to)
        if aer_balance < gas_limit*self.gas_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        tx_hash = unlock(aergo_to, receiver, burn_proof, asset_address,
                         bridge_to, gas_limit, self.gas_price)
        logger.info('\U0001f513 Unlock success: %s', tx_hash)

        # new balance on origin
        balance = get_balance(receiver, asset_address, aergo_to)
        logger.info(
            "\U0001f4b0 %s balance on destination after transfer: %s",
            asset_name, balance/10**18
        )

        aergo_to.disconnect()
        aergo_from.disconnect()
        return tx_hash

    def bridge_transfer(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        amount: int,
        receiver: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> None:
        try:
            self.config_data(
                'networks', to_chain, "tokens", asset_name, "pegs", from_chain)
            return self.transfer_from_sidechain(
                from_chain, to_chain, asset_name, amount, receiver,
                privkey_name, privkey_pwd
            )
        except KeyError:
            return self.transfer_to_sidechain(
                from_chain, to_chain, asset_name, amount, receiver,
                privkey_name, privkey_pwd
            )
