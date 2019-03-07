import hashlib
import json
import time

import aergo.herapy as herapy

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
from wallet.token_deployer import (
    deploy_token,
)
from wallet.exceptions import (
    InvalidArgumentsError,
    InsufficientBalanceError,
    TxError,
)

COMMIT_TIME = 3


class Wallet:
    """ A wallet loads it's private key from config.json and
    implements the functionality to transfer tokens to sidechains
    """

    def __init__(self, config_file_path):
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        self._config_data = config_data
        self._config_path = config_file_path

    def config_data(self, *json_path, value=None):
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

    def save_config(self, path=None):
        if path is None:
            path = self._config_path
        with open(path, "w") as f:
            json.dump(self._config_data, f, indent=4, sort_keys=True)

    def _load_priv_key(self, key_name='default'):
        """ Load and prompt user password to decrypt priv_key."""
        # TODO don't store priv_key in config.json, only it's name and path to
        # file
        priv_key = self.config_data('wallet', 'priv_key')
        return priv_key

    def _get_wallet_address(self, account_name='default'):
        # TODO store different account names for different keys in wallet
        addr = self.config_data('wallet', 'addr')
        return addr

    def _connect_aergo(self, network_name):
        aergo = herapy.Aergo()
        aergo.connect(self.config_data(network_name, 'ip'))
        return aergo

    def get_aergo(
        self,
        privkey_name,
        network_name,
        skip_state=False
    ):
        """ Return aergo provider with new account created with
        priv_key
        """
        priv_key = self._load_priv_key(privkey_name)
        if network_name is None:
            raise InvalidArgumentsError("Provide network_name")
        aergo = self._connect_aergo(network_name)
        aergo.new_account(private_key=priv_key, skip_state=skip_state)
        return aergo

    def get_balance(
        self,
        account_addr=None,
        asset_name=None,
        asset_origin_chain=None,
        asset_addr=None,
        aergo=None,
        network_name=None,
        account_name=None,
    ):
        """ Get an account or the default wallet balance of Aer
        or any token on a given network.
        usages:
            get_balance(asset_name, asset_origin_chain, network_name)
            get_balance(asset_name, network_name)
                -> asset_name was issued on network_name :asset_origin_chain
                defaults to network name
            get_balance(asset_addr, network_name)
            get_balance(asset_addr, aergo_provider)
            ...
        """
        balance = 0
        disconnect_me = False
        if account_addr is None:
            account_addr = self._get_wallet_address(account_name)
        if aergo is None:
            aergo = self._connect_aergo(network_name)
            disconnect_me = True
        if (asset_name == "aergo" and asset_origin_chain is None) \
                or asset_addr == "aergo":
            # query aergo bits on network_name
            ret_account = aergo.get_account(address=account_addr)
            balance = ret_account.balance
            asset_addr = asset_name
        else:
            if asset_addr is None:
                if asset_name is None or network_name is None:
                    raise InvalidArgumentsError("Provide asset address "
                                                "or name and origin")
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
            balance_q = aergo.query_sc_state(asset_addr,
                                             ["_sv_Balances-" +
                                              account_addr
                                              ])
            if balance_q.var_proofs[0].inclusion:
                balance = json.loads(balance_q.var_proofs[0].value)['_bignum']
        if disconnect_me:
            aergo.disconnect()
        return int(balance), asset_addr

    def get_minteable_balance(
        self,
        from_chain,
        to_chain,
        asset_name,
        asset_origin_chain,
        **kwargs
    ):
        """ Get the balance that has been locked on one side of the
        bridge and not yet minted on the other side
        """
        return self._bridge_withdrawable_balance("_sv_Locks-", "_sv_Mints-",
                                                 from_chain, to_chain,
                                                 asset_name,
                                                 asset_origin_chain,
                                                 **kwargs)

    def get_unlockeable_balance(
        self,
        from_chain,
        to_chain,
        asset_name,
        asset_origin_chain,
        **kwargs
    ):
        """ Get the balance that has been burnt on one side of the
        bridge and not yet unlocked on the other side
        """
        return self._bridge_withdrawable_balance("_sv_Burns-", "_sv_Unlocks-",
                                                 from_chain, to_chain,
                                                 asset_name,
                                                 asset_origin_chain,
                                                 **kwargs)

    def _bridge_withdrawable_balance(
        self,
        deposit_key,
        withdraw_key,
        from_chain,
        to_chain,
        asset_name,
        asset_origin_chain,
        account_name=None,
        account_addr=None,
        total_deposit=None,
        pending=False
    ):
        """ Get the balance that has been locked/burnt on one side of the
        bridge and not yet minted/unlocked on the other side.
        Calculates the difference between the total amount deposited and
        total amount withdrawn.
        Set pending to true to include deposits than have not yet been anchored
        """
        if account_addr is None:
            account_addr = self._get_wallet_address(account_name)
        asset_address_origin = self.config_data(asset_origin_chain, 'tokens',
                                                asset_name, 'addr')
        account_ref = account_addr + asset_address_origin
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)

        total_withdrawn = 0
        if total_deposit is None:
            total_deposit = 0
            block_height = 0
            if pending:
                # get the height of the latest aergo_from height (includes non
                # finalized deposits).
                _, block_height = aergo_from.get_blockchain_status()
                withdraw_proof = aergo_to.query_sc_state(
                    bridge_to, [withdraw_key + account_ref], compressed=False
                )
                if withdraw_proof.var_proofs[0].inclusion:
                    total_withdrawn = int(withdraw_proof.var_proofs[0].value
                                          .decode('utf-8')[1:-1])
            else:
                # get the height for the last anchored block on aergo_to (only
                # finalized deposits
                withdraw_proof = aergo_to.query_sc_state(
                    bridge_to, ["_sv_Height", withdraw_key + account_ref],
                    compressed=False
                )
                if withdraw_proof.var_proofs[1].inclusion:
                    total_withdrawn = int(withdraw_proof.var_proofs[1].value
                                          .decode('utf-8')[1:-1])
                block_height = int(withdraw_proof.var_proofs[0].value)

            # calculate total deposit at block_height
            block_from = aergo_from.get_block(
                block_height=block_height
            )
            deposit_proof = aergo_from.query_sc_state(
                bridge_from, [deposit_key + account_ref],
                root=block_from.blocks_root_hash, compressed=False
            )
            if deposit_proof.var_proofs[0].inclusion:
                total_deposit = int(deposit_proof.var_proofs[0].value
                                    .decode('utf-8')[1:-1])
        else:
            withdraw_proof = aergo_to.query_sc_state(
                bridge_to, [withdraw_key + account_ref], compressed=False
            )
            if withdraw_proof.var_proofs[0].inclusion:
                total_withdrawn = int(withdraw_proof.var_proofs[0].value
                                      .decode('utf-8')[1:-1])
        aergo_from.disconnect()
        aergo_to.disconnect()
        return total_deposit - total_withdrawn

    def get_bridge_tempo(
        self,
        from_chain,
        to_chain,
        aergo=None,
        bridge_address=None,
        sync=False
    ):
        """ Return the anchoring periode of from_chain onto to_chain
        and minimum finality time of from_chain
        """
        if not sync:
            t_anchor = self.config_data(to_chain, 'bridges', from_chain,
                                        "t_anchor")
            t_final = self.config_data(to_chain, 'bridges', from_chain,
                                       "t_final")
            return t_anchor, t_final
        print("\nGetting latest t_anchor and t_final from bridge contract...")
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

    def transfer(
        self,
        value,
        to,
        asset_name=None,
        asset_origin_chain=None,
        asset_addr=None,
        aergo=None,
        privkey_name=None,
        network_name=None
    ):
        """ usage:
            transfer(value, to, asset_name, asset_origin_chain, network_name)
            transfer(value, to, asset_name, network_name)
                -> asset_name was issued on network_name :asset_origin_chain
                defaults to network name
            transfer(value, to, asset_addr, network_name)
            transfer(value, to, asset_addr, aergo_provider)
            ...
        """
        if asset_name is None and asset_addr is None:
            raise InvalidArgumentsError("specify asset to transfer")
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(privkey_name, network_name)
            disconnect_me = True
        else:
            aergo.get_account()  # get the latest nonce for making tx
        sender = aergo.account.address.__str__()

        balance, asset_addr = self.get_balance(sender,
                                               asset_name, asset_origin_chain,
                                               asset_addr, aergo,
                                               network_name)
        if balance < value:
            raise InsufficientBalanceError("not enough balance")

        if asset_addr == "aergo":
            # transfer aer on network_name
            tx, result = aergo.send_payload(to_address=to,
                                            amount=value, payload=None)
        else:
            # transfer token (issued or pegged) on network_name
            tx, result = aergo.call_sc(asset_addr, "transfer",
                                       args=[to, str(value)],
                                       amount=0)
        if result.status != herapy.CommitStatus.TX_OK:
            raise TxError("Transfer asset Tx commit failed : {}"
                          .format(result))

        time.sleep(COMMIT_TIME)
        # Check lock success
        result = aergo.get_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            raise TxError("Transfer asset Tx execution failed : {}"
                          .format(result))

        print("Transfer success")
        if disconnect_me:
            aergo.disconnect()
        return True

    def get_signed_transfer(
        self,
        asset_address,
        value,
        to,
        fee=0,
        deadline=0,
        aergo=None,
        privkey_name=None,
        network_name=None
    ):
        """Sign a standard token transfer to be broadcasted by a 3rd party"""
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(privkey_name, network_name,
                                   skip_state=True)  # state not needed
            disconnect_me = True
        # get current balance and nonce
        sender = aergo.account.address.__str__()
        initial_state = aergo.query_sc_state(asset_address,
                                             ["_sv_Balances-" + sender,
                                              "_sv_Nonces-" + sender,
                                              "_sv_ContractID"
                                              ])
        balance_p, nonce_p, contractID_p = \
            [item.value for item in initial_state.var_proofs]
        balance = int(json.loads(balance_p)["_bignum"])

        try:
            nonce = int(nonce_p)
        except ValueError:
            nonce = 0

        contractID = str(contractID_p[1:-1], 'utf-8')
        msg = bytes(to + str(value) + str(nonce) + str(fee) +
                    str(deadline) + contractID, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = aergo.account.private_key.sign_msg(h).hex()

        if disconnect_me:
            aergo.disconnect()
        return nonce, sig, balance

    # TODO create a tx broadcaster that calls signed transfer,
    # lock or burn with a signature. gRPC with params arguments

    def deploy_token(
        self,
        payload_str,
        asset_name,
        total_supply,
        network_name='mainnet',
        aergo=None,
        receiver=None,
        privkey_name=None,
    ):
        """ Deploy a new standard token, store the address in
        config_data
        """
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(privkey_name, network_name)
            disconnect_me = True
        else:
            aergo.get_account()  # get latest nonce for tx

        if receiver is None:
            receiver = aergo.account.address.__str__()
        print("  > Sender Address: {}".format(receiver))

        sc_address = deploy_token(payload_str, aergo, receiver, total_supply)

        print("------ Store addresse in config.json -----------")
        self.config_data(network_name, 'tokens', asset_name, value={})
        self.config_data(network_name, 'tokens', asset_name, 'addr',
                         value=sc_address)
        self.config_data(network_name, 'tokens', asset_name, 'pegs',
                         value={})
        self.save_config()
        if disconnect_me:
            aergo.disconnect()
        return True

    def transfer_to_sidechain(
        self,
        from_chain,
        to_chain,
        asset_name,
        amount,
        sender=None,
        receiver=None,
        privkey_name=None
    ):
        """ Transfer assets from from_chain to to_chain.
        The asset being transfered to the to_chain sidechain
        should be native of from_chain
        """
        _, t_final = self.get_bridge_tempo(from_chain, to_chain, sync=True)

        lock_height = self.initiate_transfer_lock(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, privkey_name)
        minteable = self.get_minteable_balance(from_chain, to_chain,
                                               asset_name, from_chain,
                                               pending=True)
        print("pending mint: ", minteable)
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final-COMMIT_TIME)

        self.finalize_transfer_mint(from_chain, to_chain, asset_name,
                                    receiver, lock_height, privkey_name)

    def transfer_from_sidechain(
        self,
        from_chain,
        to_chain,
        asset_name,
        amount,
        sender=None,
        receiver=None,
        privkey_name=None
    ):
        """ Transfer assets from from_chain to to_chain
        The asset being transfered back to the to_chain native chain
        should be a minted asset on the sidechain.
        """
        _, t_final = self.get_bridge_tempo(from_chain, to_chain, sync=True)

        burn_height = self.initiate_transfer_burn(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, privkey_name)
        unlockeable = self.get_unlockeable_balance(from_chain, to_chain,
                                                   asset_name, to_chain,
                                                   pending=True)
        print("pending unlock: ", unlockeable)
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final-COMMIT_TIME)

        self.finalize_transfer_unlock(from_chain, to_chain, asset_name,
                                      receiver, burn_height, privkey_name)

    def initiate_transfer_lock(
        self,
        from_chain,
        to_chain,
        asset_name,
        amount,
        sender=None,
        receiver=None,
        privkey_name=None
    ):
        """ Initiate a transfer to a sidechain by locking the asset."""
        priv_key = self._load_priv_key(privkey_name)

        aergo_from = self._connect_aergo(from_chain)

        # locker_account is the owner of tokens/aergo.
        # merkle_bridge.lua.lock() supports delegated token locks.
        locker_account = aergo_from.new_account(private_key=priv_key)
        if sender is None:
            sender = locker_account.address.__str__()
        if receiver is None:
            receiver = sender

        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')

        print("\n\n------ Lock {} -----------".format(asset_name))
        asset_address = self.config_data(from_chain, 'tokens',
                                         asset_name, 'addr')
        balance = 0
        signed_transfer = None
        if asset_name == "aergo":
            balance, _ = self.get_balance(sender,
                                          asset_addr=asset_address,
                                          aergo=aergo_from)
        else:
            nonce, signature, balance = self.get_signed_transfer(
                asset_address, amount, bridge_from, aergo=aergo_from
            )
            signed_transfer = [nonce, signature]
        print("{} balance on origin before transfer: {}"
              .format(asset_name, balance/10**18))
        if balance < amount:
            raise InsufficientBalanceError("not enough balance")

        lock_height = lock(aergo_from, bridge_from,
                           receiver, amount, asset_address,
                           signed_transfer)

        # remaining balance on origin : aer or asset
        balance, _ = self.get_balance(sender,
                                      asset_addr=asset_address,
                                      aergo=aergo_from)
        print("Remaining {} balance on origin after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()
        return lock_height

    def finalize_transfer_mint(
        self,
        from_chain,
        to_chain,
        asset_name,
        receiver=None,
        lock_height=0,
        privkey_name=None
    ):
        """
        Finalize a transfer of assets to a sidechain by minting then
        after the lock is final and a new anchor was made.
        NOTE anybody can mint so sender is not necessary.
        The amount to mint is the difference between total deposit and
        already minted amount.
        Bridge tempo is taken from config_data
        """
        priv_key = self._load_priv_key(privkey_name)

        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        minter_account = aergo_to.new_account(private_key=priv_key)
        if receiver is None:
            receiver = minter_account.address.__str__()

        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')

        t_anchor, t_final = self.get_bridge_tempo(from_chain, to_chain)

        print("\n------ Get lock proof -----------")
        asset_address = self.config_data(from_chain, 'tokens',
                                         asset_name, 'addr')
        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      asset_address, t_anchor, t_final)

        print("\n\n------ Mint {} on destination blockchain -----------"
              .format(asset_name))
        save_pegged_token_address = False
        try:
            token_pegged = self.config_data(from_chain, 'tokens', asset_name,
                                            'pegs', to_chain)
            balance, _ = self.get_balance(receiver, asset_addr=token_pegged,
                                          aergo=aergo_to)
            print("{} balance on destination before transfer : {}"
                  .format(asset_name, balance/10**18))
        except KeyError:
            print("Pegged token unknow by wallet")
            save_pegged_token_address = True

        token_pegged = mint(aergo_to, receiver, lock_proof, asset_address,
                            bridge_to)

        # new balance on sidechain
        balance, _ = self.get_balance(receiver, asset_addr=token_pegged,
                                      aergo=aergo_to)
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

    def initiate_transfer_burn(
        self,
        from_chain,
        to_chain,
        asset_name,
        amount,
        sender=None,
        receiver=None,
        privkey_name=None
    ):
        """ Initiate a transfer from a sidechain by burning the assets."""
        priv_key = self._load_priv_key(privkey_name)

        aergo_from = self._connect_aergo(from_chain)

        burner_account = aergo_from.new_account(private_key=priv_key)

        if sender is None:
            # minted token currently doesnt support delegated burn
            sender = burner_account.address.__str__()
        if receiver is None:
            receiver = sender

        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')
        token_pegged = self.config_data(to_chain, 'tokens', asset_name, 'pegs',
                                        from_chain)

        print("\n\n------ Burn {}-----------".format(asset_name))
        token_pegged = self.config_data(to_chain, 'tokens', asset_name, 'pegs',
                                        from_chain)
        balance, _ = self.get_balance(sender, asset_addr=token_pegged,
                                      aergo=aergo_from)
        print("{} balance on sidechain before transfer: {}"
              .format(asset_name, balance/10**18))
        if balance < amount:
            raise InsufficientBalanceError("not enough balance")

        burn_height = burn(aergo_from, sender, receiver, amount,
                           token_pegged, bridge_from)

        # remaining balance on sidechain
        balance, _ = self.get_balance(sender, asset_addr=token_pegged,
                                      aergo=aergo_from)
        print("Remaining {} balance on sidechain after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()

        return burn_height

    def finalize_transfer_unlock(
        self,
        from_chain,
        to_chain,
        asset_name,
        receiver=None,
        burn_height=0,
        privkey_name=None,
    ):
        """
        Finalize a transfer of assets from a sidechain by unlocking then
        after the burn is final and a new anchor was made.
        NOTE anybody can unlock so sender is not necessary.
        The amount to unlock is the difference between total burn and
        already unlocked amount.
        Bridge tempo is taken from config_data
        """
        priv_key = self._load_priv_key(privkey_name)

        aergo_to = self._connect_aergo(to_chain)
        aergo_from = self._connect_aergo(from_chain)
        unlocker_account = aergo_to.new_account(private_key=priv_key)
        if receiver is None:
            receiver = unlocker_account.address.__str__()

        bridge_to = self.config_data(to_chain, 'bridges', from_chain, 'addr')
        bridge_from = self.config_data(from_chain, 'bridges', to_chain, 'addr')

        t_anchor, t_final = self.get_bridge_tempo(from_chain, to_chain)

        print("\n------ Get burn proof -----------")
        asset_address = self.config_data(to_chain, 'tokens', asset_name,
                                         'addr')
        burn_proof = build_burn_proof(aergo_to, aergo_from, receiver,
                                      bridge_to, bridge_from, burn_height,
                                      asset_address, t_anchor, t_final)

        print("\n\n------ Unlock {} on origin blockchain -----------"
              .format(asset_name))
        balance, _ = self.get_balance(receiver,
                                      asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination before transfer: {}"
              .format(asset_name, balance/10**18))

        unlock(aergo_to, receiver, burn_proof, asset_address, bridge_to)

        # new balance on origin
        balance, _ = self.get_balance(receiver,
                                      asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_to.disconnect()
        aergo_from.disconnect()


if __name__ == '__main__':

    selection = 0

    wallet = Wallet("./config.json")

    if selection == 0:
        amount = 1*10**18
        asset = 'aergo'
        wallet.transfer_to_sidechain('mainnet',
                                     'sidechain2',
                                     asset,
                                     amount)
        balance, _ = wallet.get_balance(asset_name=asset,
                                        asset_origin_chain='mainnet',
                                        network_name='sidechain2')
        print("Get {} balance on sidechain2 : {}".format(asset, balance))
        wallet.transfer_from_sidechain('sidechain2',
                                       'mainnet',
                                       asset,
                                       amount)
    elif selection == 1:
        with open("./contracts/token_bytecode.txt", "r") as f:
            payload_str = f.read()[:-1]
        total_supply = 500*10**6*10**18
        wallet.deploy_token(payload_str, "token2", total_supply)
    elif selection == 2:
        to = wallet._config_data['validators'][0]['addr']
        sender = wallet._config_data['wallet']['addr']
        asset = 'token1'
        amount = 2
        result = wallet.get_balance(to, asset_name=asset,
                                    network_name='mainnet')
        print('receiver balance before', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    network_name='mainnet')
        print('sender balance before', result)

        wallet.transfer(amount, to, asset_name=asset, network_name='mainnet')

        result = wallet.get_balance(to, asset_name=asset,
                                    network_name='mainnet')
        print('receiver balance result', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    network_name='mainnet')
        print('sender balance after', result)

        # transfer a pegged token
        wallet.transfer_to_sidechain('mainnet',
                                     'sidechain2',
                                     asset,
                                     amount)
        result = wallet.get_balance(to, asset_name=asset,
                                    asset_origin_chain='mainnet',
                                    network_name='sidechain2')
        print('receiver balance before', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    asset_origin_chain='mainnet',
                                    network_name='sidechain2')
        print('sender balance before', result)

        wallet.transfer(amount, to, asset_name=asset,
                        asset_origin_chain='mainnet',
                        network_name='sidechain2')

        result = wallet.get_balance(to, asset_name=asset,
                                    asset_origin_chain='mainnet',
                                    network_name='sidechain2')
        print('receiver balance after', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    asset_origin_chain='mainnet',
                                    network_name='sidechain2')
        print('sender balance after', result)
