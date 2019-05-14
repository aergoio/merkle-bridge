from getpass import getpass
import json

from typing import (
    Union,
    Tuple,
    List,
    Dict,
    Optional,
)

import aergo.herapy as herapy
from aergo.herapy.errors.general_exception import (
    GeneralException,
)

from broadcaster.broadcaster_pb2 import (
    ExecutionStatus,
)

from wallet.transfer_to_sidechain import (
    lock,
    build_lock_proof,
    mint,
)
from wallet.transfer_from_sidechain import (
    burn,
    build_burn_proof,
    unlock,
)
from wallet.exceptions import (
    InvalidArgumentsError,
    InsufficientBalanceError,
    BroadcasterError,
)
from wallet.wallet_utils import (
    get_balance,
    transfer,
    get_signed_transfer,
    verify_signed_transfer,
    broadcast_simple_transfer,
    broadcast_bridge_transfer,
    bridge_withdrawable_balance,
    wait_finalization
)
from wallet.token_deployer import (
    deploy_token,
)


class Wallet:
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
        self.fee_price = 0

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
                print("Passwords don't match, try again")
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
            self.config_data('wallet', account_name,
                             'priv_key', value=exported_privkey)
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
        self.config_data(origin_chain_name, 'tokens', asset_name, value={})
        self.config_data(origin_chain_name, 'tokens', asset_name, 'addr',
                         value=addr_on_origin_chain)
        self.config_data(origin_chain_name, 'tokens', asset_name, 'pegs',
                         value={})
        if pegged_chain_name is not None and addr_on_pegged_chain is not None:
            self.config_data(origin_chain_name, 'tokens', asset_name, 'pegs',
                             pegged_chain_name, value=addr_on_pegged_chain)
        self.save_config()

    def _connect_aergo(self, network_name: str) -> herapy.Aergo:
        aergo = herapy.Aergo()
        aergo.connect(self.config_data(network_name, 'ip'))
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
            print("Decrypt exported private key '{}'".format(privkey_name))
            while True:
                try:
                    privkey_pwd = getpass("Password: ")
                    aergo.import_account(exported_privkey, privkey_pwd,
                                         skip_state=skip_state)
                except GeneralException:
                    print("Wrong password, try again")
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
            asset_addr = self.config_data(network_name, 'tokens',
                                          asset_name, 'addr')
        else:
            # query a pegged token (from asset_origin_chain) balance
            # on network_name sidechain (token or aer)
            asset_addr = self.config_data(asset_origin_chain, 'tokens',
                                          asset_name, 'pegs',
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
        asset_addr = self.get_asset_address(asset_name, network_name,
                                            asset_origin_chain)
        balance = get_balance(account_addr, asset_addr, aergo)
        aergo.disconnect()
        return balance, asset_addr

    def get_minteable_balance(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        account_name: str = 'default',
        account_addr: str = None,
        total_deposit: int = None,
        pending: bool = False
    ) -> int:
        """ Get the balance that has been locked on one side of the
        bridge and not yet minted on the other side
        Calculates the difference between the total amount deposited and
        total amount withdrawn.
        Set pending to true to include deposits than have not yet been anchored
        """
        if account_addr is None:
            account_addr = self.get_wallet_address(account_name)
        asset_address_origin = self.config_data(from_chain, 'tokens',
                                                asset_name, 'addr')
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        withdrawable = bridge_withdrawable_balance(
            account_addr, asset_address_origin, bridge_from, bridge_to,
            aergo_from, aergo_to, True, total_deposit, pending
        )
        aergo_from.disconnect()
        aergo_to.disconnect()
        return withdrawable

    def get_unlockeable_balance(
        self,
        from_chain: str,
        to_chain: str,
        asset_name: str,
        account_name: str = 'default',
        account_addr: str = None,
        total_deposit: int = None,
        pending: bool = False
    ) -> int:
        """ Get the balance that has been burnt on one side of the
        bridge and not yet unlocked on the other side
        Calculates the difference between the total amount deposited and
        total amount withdrawn.
        Set pending to true to include deposits than have not yet been anchored
        """
        if account_addr is None:
            account_addr = self.get_wallet_address(account_name)
        asset_address_origin = self.config_data(to_chain, 'tokens',
                                                asset_name, 'addr')
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        withdrawable = bridge_withdrawable_balance(
            account_addr, asset_address_origin, bridge_from, bridge_to,
            aergo_from, aergo_to, False, total_deposit, pending
        )
        aergo_from.disconnect()
        aergo_to.disconnect()
        return withdrawable

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
            t_anchor = self.config_data(to_chain, 'bridges', from_chain,
                                        "t_anchor")
            t_final = self.config_data(to_chain, 'bridges', from_chain,
                                       "t_final")
            return t_anchor, t_final
        print("\ngetting latest t_anchor and t_final from bridge contract...")
        if aergo is None:
            aergo = self._connect_aergo(to_chain)
        if bridge_address is None:
            bridge_address = self.config_data(to_chain, 'bridges',
                                              from_chain, 'addr')
        # Get bridge information
        bridge_info = aergo.query_sc_state(bridge_address,
                                           ["_sv_T_anchor",
                                            "_sv_T_final",
                                            ])
        t_anchor, t_final = [int(item.value)
                             for item in bridge_info.var_proofs]
        aergo.disconnect()
        self.config_data(to_chain, 'bridges', from_chain, "t_anchor",
                         value=t_anchor)
        self.config_data(to_chain, 'bridges', from_chain, "t_final",
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
            fee_limit = 0
            if balance < value + fee_limit*self.fee_price:
                raise InsufficientBalanceError("not enough balance")
        else:
            fee_limit = 0
            if balance < value:
                raise InsufficientBalanceError("not enough token balance")
            aer_balance, _ = self.get_balance(
                'aergo', network_name, account_addr=sender
            )
            if aer_balance < fee_limit*self.fee_price:
                err = "not enough aer balance to pay tx fee"
                raise InsufficientBalanceError(err)

        tx_hash = transfer(value, to, asset_addr, aergo, sender, fee_limit,
                           self.fee_price)
        aergo.disconnect()
        return tx_hash

    def _d_transfer(
        self,
        value: int,
        fee: int,
        to: str,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        signed_transfer, balance = self.get_signed_transfer(
            value, to, asset_name, network_name, asset_origin_chain, fee,
            execute_before, privkey_name, privkey_pwd
        )
        if balance < value + fee:
            raise InsufficientBalanceError("not enough balance")
        # call  broadcaster
        br_ip = self.config_data('broadcasters', network_name, 'ip')
        is_pegged = False
        if asset_origin_chain is not None:
            is_pegged = True
        owner = self.get_wallet_address(privkey_name)
        return broadcast_simple_transfer(
            br_ip, owner, asset_name, value, signed_transfer, is_pegged, to
        )

    def d_transfer(
        self,
        value: int,
        fee: int,
        to: str,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        balance, _ = self.get_balance(
            asset_name, network_name, asset_origin_chain,
            account_name=privkey_name
        )
        print("sender : {} balance before transfer: {}"
              .format(asset_name, balance/10**18))
        balance, _ = self.get_balance(
            asset_name, network_name, asset_origin_chain,
            account_addr=to
        )
        print("receiver : {} balance before transfer: {}"
              .format(asset_name, balance/10**18))
        # Broadcast transfer
        broadcasted = self._d_transfer(
            value, fee, to, asset_name, network_name, asset_origin_chain,
            privkey_name, privkey_pwd, execute_before)
        if broadcasted.error:
            raise BroadcasterError(broadcasted)

        balance, _ = self.get_balance(
            asset_name, network_name, asset_origin_chain,
            account_name=privkey_name
        )
        print("sender : {} balance before transfer: {}"
              .format(asset_name, balance/10**18))
        balance, _ = self.get_balance(
            asset_name, network_name, asset_origin_chain,
            account_addr=to
        )
        print("receiver : {} balance before transfer: {}"
              .format(asset_name, balance/10**18))
        return broadcasted

    def get_signed_transfer(
        self,
        value: int,
        to: str,
        asset_name: str,
        network_name: str,
        asset_origin_chain: str = None,
        fee: int = 0,
        execute_before: int = 0,
        privkey_name: str = 'default',
        privkey_pwd: str = None
    ) -> Tuple[Tuple[int, str, str, int], int]:
        """Sign a standard token transfer to be broadcasted by a 3rd party"""
        asset_addr = self.get_asset_address(asset_name, network_name,
                                            asset_origin_chain)
        aergo = self.get_aergo(network_name, privkey_name, privkey_pwd,
                               skip_state=True)  # state not needed
        # create signed transfer
        signed_transfer, balance = get_signed_transfer(
            value, to, asset_addr, aergo, fee, execute_before
        )
        aergo.disconnect()
        return signed_transfer, balance

    def verify_signed_transfer(
        self,
        value: int,
        sender: str,
        to: str,
        asset_name: str,
        network_name: str,
        signed_transfer: Tuple[int, str, str, int],
        deadline_margin: int,
        asset_origin_chain: str = None
    ) -> Tuple[bool, str]:
        """ Verify a signed token transfer is valid"""
        asset_addr = self.get_asset_address(asset_name, network_name,
                                            asset_origin_chain)
        aergo = self._connect_aergo(network_name)
        return verify_signed_transfer(
            sender, to, asset_addr, value, signed_transfer, aergo,
            deadline_margin
        )

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
        print("  > Sender Address: {}".format(receiver))

        fee_limit = 0
        sc_address = deploy_token(payload_str, aergo, receiver, total_supply,
                                  fee_limit, self.fee_price)

        print("------ Store address in config.json -----------")
        self.config_data(network_name, 'tokens', asset_name, value={})
        self.config_data(network_name, 'tokens', asset_name, 'addr',
                         value=sc_address)
        self.config_data(network_name, 'tokens', asset_name, 'pegs',
                         value={})
        self.save_config()
        aergo.disconnect()
        return sc_address

    def _d_transfer_to_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        token_name: str,
        amount: int,
        fee: int,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        """ Create a delegated token transfer with a fee that the broadcaster
        will collect for executing the transaction.
        """
        # create signed transfer
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        signed_transfer, balance = self.get_signed_transfer(
            amount, bridge_from, token_name, from_chain, fee=fee,
            execute_before=execute_before, privkey_name=privkey_name,
            privkey_pwd=privkey_pwd
        )
        if balance < amount + fee:
            raise InsufficientBalanceError("not enough balance")
        # call  broadcaster
        br_ip = self.config_data('broadcasters', from_chain, to_chain, 'ip')
        owner = self.get_wallet_address(privkey_name)
        return broadcast_bridge_transfer(br_ip, owner, token_name, amount,
                                         signed_transfer)

    def d_transfer_to_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        token_name: str,
        amount: int,
        fee: int,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        """ Create a delegated token transfer with a fee that the broadcaster
        will collect for executing the transaction.
        """
        balance, _ = self.get_balance(token_name, from_chain,
                                      account_name=privkey_name)
        print("{} balance on origin before transfer: {}"
              .format(token_name, balance/10**18))
        save_pegged_token_address = False
        try:
            balance, _ = self.get_balance(token_name, to_chain,
                                          asset_origin_chain=from_chain,
                                          account_name=privkey_name)
            print("{} balance on sidechain before transfer: {}"
                  .format(token_name, balance/10**18))
        except KeyError:
            print("Pegged token unknow by wallet")
            save_pegged_token_address = True

        print("waiting for broadcaster...")
        broadcasted = self._d_transfer_to_sidechain(
           from_chain, to_chain, token_name, amount, fee, privkey_name,
           privkey_pwd, execute_before
        )
        if broadcasted.error:
            raise BroadcasterError(broadcasted)

        if save_pegged_token_address:
            print("\n------ Store mint address in config.json -----------")
            aergo = self._connect_aergo(to_chain)
            mint_result = aergo.get_tx_result(broadcasted.withdraw_tx_hash)
            token_pegged = json.loads(mint_result.detail)[0]
            self.config_data(from_chain, 'tokens', token_name, 'pegs',
                             to_chain, value=token_pegged)
            self.save_config()

        balance, _ = self.get_balance(token_name, from_chain,
                                      account_name=privkey_name)
        print("{} balance on origin after transfer: {}"
              .format(token_name, balance/10**18))
        balance, _ = self.get_balance(token_name, to_chain,
                                      asset_origin_chain=from_chain,
                                      account_name=privkey_name)
        print("{} balance on sidechain after transfer: {}"
              .format(token_name, balance/10**18))
        return broadcasted

    def _d_transfer_from_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        token_name: str,
        amount: int,
        fee: int,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        """ Create a delegated token transfer with a fee that the broadcaster
        will collect for executing the transaction.
        """
        # create signed transfer
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        signed_transfer, balance = self.get_signed_transfer(
            amount, bridge_from, token_name, from_chain,
            asset_origin_chain=to_chain, fee=fee,
            execute_before=execute_before, privkey_name=privkey_name,
            privkey_pwd=privkey_pwd
        )
        if balance < amount + fee:
            raise InsufficientBalanceError("not enough balance")
        # call  broadcaster
        br_ip = self.config_data('broadcasters', to_chain, from_chain, 'ip')
        owner = self.get_wallet_address(privkey_name)
        return broadcast_bridge_transfer(br_ip, owner, token_name, amount,
                                         signed_transfer, True)

    def d_transfer_from_sidechain(
        self,
        from_chain: str,
        to_chain: str,
        token_name: str,
        amount: int,
        fee: int,
        privkey_name: str = 'default',
        privkey_pwd: str = None,
        execute_before: int = 30
    ) -> ExecutionStatus:
        """ Create a delegated token transfer with a fee that the broadcaster
        will collect for executing the transaction.
        """
        balance, _ = self.get_balance(token_name, to_chain,
                                      account_name=privkey_name)
        print("{} balance on destination before transfer: {}"
              .format(token_name, balance/10**18))
        balance, _ = self.get_balance(token_name, from_chain,
                                      asset_origin_chain=to_chain,
                                      account_name=privkey_name)
        print("{} balance on sidechain before transfer: {}"
              .format(token_name, balance/10**18))

        print("waiting for broadcaster...")
        broadcasted = self._d_transfer_from_sidechain(
            from_chain, to_chain, token_name, amount, fee, privkey_name,
            privkey_pwd, execute_before
        )
        if broadcasted.error:
            raise BroadcasterError(broadcasted)

        balance, _ = self.get_balance(token_name, to_chain,
                                      account_name=privkey_name)
        print("{} balance on destination after transfer: {}"
              .format(token_name, balance/10**18))
        balance, _ = self.get_balance(token_name, from_chain,
                                      asset_origin_chain=to_chain,
                                      account_name=privkey_name)
        print("{} balance on sidechain after transfer: {}"
              .format(token_name, balance/10**18))
        return broadcasted

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
        minteable = self.get_minteable_balance(
            from_chain, to_chain, asset_name, account_addr=receiver,
            pending=True
        )
        print("pending mint: ", minteable)
        print("waiting finalisation ...")
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
        unlockeable = self.get_unlockeable_balance(
            from_chain, to_chain, asset_name, account_addr=receiver,
            pending=True
        )
        print("pending unlock: ", unlockeable)
        print("waiting finalisation ...")
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
        aergo_from = self.get_aergo(from_chain, privkey_name, privkey_pwd)
        sender = str(aergo_from.account.address)
        if receiver is None:
            receiver = sender
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        asset_address = self.config_data(from_chain, 'tokens',
                                         asset_name, 'addr')
        balance = 0
        signed_transfer: Optional[Union[Tuple[int, str],
                                        Tuple[int, str, str, int]]] = None
        if asset_name == 'aergo':
            # transfer aer
            fee_limit = 0
            balance = get_balance(sender, asset_address, aergo_from)
            if balance < amount + fee_limit*self.fee_price:
                raise InsufficientBalanceError("not enough balance")
        else:
            # sign transfer so bridge can pull tokens to lock.
            fee_limit = 0
            signed_transfer, balance = \
                get_signed_transfer(amount, bridge_from, asset_address,
                                    aergo_from)
            signed_transfer = signed_transfer[:2]  # only nonce, sig are needed
            if balance < amount:
                raise InsufficientBalanceError("not enough token balance")
            aer_balance = get_balance(sender, 'aergo', aergo_from)
            if aer_balance < fee_limit*self.fee_price:
                err = "not enough aer balance to pay tx fee"
                raise InsufficientBalanceError(err)

        print("{} balance on origin before transfer: {}"
              .format(asset_name, balance/10**18))

        print("\n\n------ Lock {} -----------".format(asset_name))
        lock_height, tx_hash = lock(aergo_from, bridge_from,
                                    receiver, amount, asset_address, fee_limit,
                                    self.fee_price, signed_transfer)

        # remaining balance on origin : aer or asset
        balance = get_balance(sender, asset_address, aergo_from)
        print("remaining {} balance on origin after transfer: {}"
              .format(asset_name, balance/10**18))

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
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self.get_aergo(to_chain, privkey_name, privkey_pwd)
        tx_sender = str(aergo_to.account.address)
        if receiver is None:
            receiver = tx_sender
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        asset_address = self.config_data(from_chain, 'tokens',
                                         asset_name, 'addr')
        save_pegged_token_address = False
        try:
            token_pegged = self.config_data(from_chain, 'tokens', asset_name,
                                            'pegs', to_chain)
            balance = get_balance(receiver, token_pegged, aergo_to)
            print("{} balance on destination before transfer : {}"
                  .format(asset_name, balance/10**18))
        except KeyError:
            print("Pegged token unknow by wallet")
            save_pegged_token_address = True

        fee_limit = 0
        aer_balance = get_balance(tx_sender, 'aergo', aergo_to)
        if aer_balance < fee_limit*self.fee_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        print("\n------ Get lock proof -----------")
        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      asset_address)
        print("\n\n------ Mint {} on destination blockchain -----------"
              .format(asset_name))
        token_pegged, tx_hash = mint(
            aergo_to, receiver, lock_proof, asset_address, bridge_to,
            fee_limit, self.fee_price
        )

        # new balance on sidechain
        balance = get_balance(receiver, token_pegged, aergo_to)
        print("{} balance on destination after transfer : {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()
        aergo_to.disconnect()

        # record mint address in file
        if save_pegged_token_address:
            print("\n------ Store mint address in config.json -----------")
            self.config_data(from_chain, 'tokens', asset_name, 'pegs',
                             to_chain, value=token_pegged)
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
        aergo_from = self.get_aergo(from_chain, privkey_name, privkey_pwd)
        sender = str(aergo_from.account.address)
        if receiver is None:
            receiver = sender
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        token_pegged = self.config_data(to_chain, 'tokens', asset_name, 'pegs',
                                        from_chain)
        balance = get_balance(sender, token_pegged, aergo_from)
        print("{} balance on sidechain before transfer: {}"
              .format(asset_name, balance/10**18))
        if balance < amount:
            raise InsufficientBalanceError("not enough balance")

        fee_limit = 0
        aer_balance = get_balance(sender, 'aergo', aergo_from)
        if aer_balance < fee_limit*self.fee_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        print("\n\n------ Burn {}-----------".format(asset_name))
        burn_height, tx_hash = burn(aergo_from, bridge_from, receiver, amount,
                                    token_pegged, fee_limit, self.fee_price)

        # remaining balance on sidechain
        balance = get_balance(sender, token_pegged, aergo_from)
        print("remaining {} balance on sidechain after transfer: {}"
              .format(asset_name, balance/10**18))

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
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self.get_aergo(to_chain, privkey_name, privkey_pwd)
        tx_sender = str(aergo_to.account.address)
        if receiver is None:
            receiver = tx_sender
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        asset_address = self.config_data(to_chain, 'tokens', asset_name,
                                         'addr')

        print("\n------ Get burn proof -----------")
        burn_proof = build_burn_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, burn_height,
                                      asset_address)

        print("\n\n------ Unlock {} on origin blockchain -----------"
              .format(asset_name))
        balance = get_balance(receiver, asset_address, aergo_to)
        print("{} balance on destination before transfer: {}"
              .format(asset_name, balance/10**18))

        fee_limit = 0
        aer_balance = get_balance(tx_sender, 'aergo', aergo_to)
        if aer_balance < fee_limit*self.fee_price:
            err = "not enough aer balance to pay tx fee"
            raise InsufficientBalanceError(err)

        tx_hash = unlock(aergo_to, receiver, burn_proof, asset_address,
                         bridge_to, fee_limit, self.fee_price)

        # new balance on origin
        balance = get_balance(receiver, asset_address, aergo_to)
        print("{} balance on destination after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_to.disconnect()
        aergo_from.disconnect()
        return tx_hash
