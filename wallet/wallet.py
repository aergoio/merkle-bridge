import json
import time

import aergo.herapy as herapy

from wallet.transfer_to_sidechain import (
    lock_aer,
    lock_token,
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
    InvalidArguments,
)

COMMIT_TIME = 3

# TODO remove make transfer_to_sidechain... from readme and replace with wallet


class Wallet:
    """ A wallet loads it's private key from config.json and
        implements the functionality to transfer tokens to sidechains
    """

    def __init__(self, config_data, aer=False):
        self._config_data = config_data

    def _connect_aergo(self, network_name):
        aergo = herapy.Aergo()
        aergo.connect(self._config_data[network_name]['ip'])
        return aergo

    def get_balance(self, account, asset_name=None,
                    asset_addr=None, network_name=None, aergo=None):
        balance = 0
        disconnect_me = False
        if aergo is None:
            if network_name is None:
                raise InvalidArguments("Provide network_name")
            aergo = self._connect_aergo(network_name)
            disconnect_me = True
        if asset_name == "aergo":
            aergo.get_account()
            balance = aergo.account.balance
        else:
            if asset_addr is None:
                if asset_name is None or network_name is None:
                    raise InvalidArguments("Provide asset address")
                asset_addr = self._config_data[network_name]['tokens'][asset_name]['addr']
            balance_q = aergo.query_sc_state(asset_addr,
                                             ["_sv_Balances-" +
                                              account
                                              ])
            balance = json.loads(balance_q.var_proofs[0].value)['_bignum']
        if disconnect_me:
            aergo.disconnect()
        return int(balance)

    def get_bridge_tempo(self, aergo, bridge_address):
        # Get bridge information
        bridge_info = aergo.query_sc_state(bridge_address,
                                           ["_sv_T_anchor",
                                            "_sv_T_final",
                                            ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        return t_anchor, t_final

    def transfer(asset_name, amount, receiver, priv_key=None):
        # TODO delegated transfer and bridge transfer
        # TODO add priv_key_1 in wallet in config.json
        pass

    def signed_transfer():
        # signs a transfer to be given to a 3rd party
        # TODO use before calling lock
        pass

    # TODO create a tx broadcaster that calls signed transfer,
    # lock or burn with a signature. gRPC with params arguments

    def deploy_token(self, payload_str, asset_name,
                     total_supply, network_name='mainnet',
                     aergo=None, receiver=None, priv_key=None):
        disconnect_me = False
        if aergo is None:
            disconnect_me = True
            aergo = self._connect_aergo(network_name)
            if priv_key is None:
                priv_key = self._config_data['wallet']['priv_key']
            aergo.new_account(private_key=priv_key)
        if receiver is None:
            receiver = aergo.account.address.__str__()
        print("  > Sender Address: {}".format(receiver))

        sc_address = deploy_token(payload_str, aergo, receiver, total_supply)

        print("------ Store addresse in config.json -----------")
        self._config_data[network_name]['tokens'][asset_name] = {}
        self._config_data[network_name]['tokens'][asset_name]['addr'] = sc_address
        with open("./config.json", "w") as f:
            json.dump(self._config_data, f, indent=4, sort_keys=True)
        if disconnect_me:
            aergo.disconnect()

    def transfer_to_sidechain(self,
                              from_chain,
                              to_chain,
                              asset_name,
                              amount,
                              sender=None,
                              receiver=None,
                              priv_key=None):
        if priv_key is None:
            priv_key = self._config_data["wallet"]['priv_key']
        lock_height = self.initiate_transfer_lock(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        self.finalize_transfer_mint(lock_height, from_chain, to_chain,
                                    asset_name, receiver, priv_key)

    def transfer_from_sidechain(self,
                                from_chain,
                                to_chain,
                                asset_name,
                                amount,
                                sender=None,
                                receiver=None,
                                priv_key=None):
        if priv_key is None:
            priv_key = self._config_data["wallet"]['priv_key']
        burn_height = self.initiate_transfer_burn(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        self.finalize_transfer_unlock(burn_height, from_chain, to_chain,
                                      asset_name, receiver, priv_key)

    def initiate_transfer_lock(self,
                               from_chain,
                               to_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        # TODO make a new aergo if not already passed as argument != None
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_from = self._connect_aergo(from_chain)

        # locker_account is the owner of tokens/aergo.
        # merkle_bridge.lua.lock() supports delegated token locks.
        locker_account = aergo_from.new_account(private_key=priv_key)
        if sender is None:
            sender = locker_account.address.__str__()
        if receiver is None:
            receiver = sender

        bridge_from = self._config_data[from_chain]['bridges'][to_chain]

        print("\n\n------ Lock {} -----------".format(asset_name))
        asset_address = self._config_data[from_chain]['tokens'][asset_name]['addr']
        if asset_name == "aergo":
            lock_height = lock_aer(aergo_from, sender, receiver, amount,
                                   bridge_from)
        else:
            # TODO make signed transfer here, use same lock function with
            # 'aergo'?
            lock_height = lock_token(aergo_from, sender, receiver, amount,
                                     asset_address, bridge_from)
        # remaining balance on origin
        balance = self.get_balance(sender, asset_name=asset_name,
                                   asset_addr=asset_address, aergo=aergo_from)
        print("Remaining {} balance on origin after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()
        return lock_height

    def finalize_transfer_mint(self,
                               lock_height,
                               from_chain,
                               to_chain,
                               asset_name,
                               receiver=None,
                               priv_key=None):
        # NOTE anybody can mint so sender is not necessary
        # amount to mint is the difference between total deposit and
        # already minted amount
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        minter_account = aergo_to.new_account(private_key=priv_key)
        if receiver is None:
            receiver = minter_account.address.__str__()

        bridge_from = self._config_data[from_chain]['bridges'][to_chain]
        bridge_to = self._config_data[to_chain]['bridges'][from_chain]

        print("\n------ Wait finalisation and get lock proof -----------")
        asset_address = self._config_data[from_chain]['tokens'][asset_name]['addr']
        t_anchor, t_final = self.get_bridge_tempo(aergo_to, bridge_to)
        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      asset_address, t_anchor, t_final)

        print("\n\n------ Mint {} on destination blockchain -----------"
              .format(asset_name))
        try:
            token_pegged = self._config_data[from_chain]['tokens'][asset_name]['pegs'][to_chain]
            balance = self.get_balance(receiver, asset_addr=token_pegged,
                                       aergo=aergo_to)
            print("{} balance on destination before transfer : {}"
                  .format(asset_name, balance/10**18))
        except KeyError:
            # TODO get pegged address from the bridge_to contract
            print("Pegged token unknow by wallet")

        token_pegged = mint(aergo_to, receiver, lock_proof, asset_address,
                            bridge_to)

        # new balance on sidechain
        balance = self.get_balance(receiver, asset_addr=token_pegged,
                                   aergo=aergo_to)
        print("{} balance on destination after transfer : {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()
        aergo_to.disconnect()

        # record mint address in file
        print("\n------ Store mint address in config.json -----------")
        self._config_data[from_chain]['tokens'][asset_name]['pegs'][to_chain] = token_pegged
        with open("./config.json", "w") as f:
            json.dump(self._config_data, f, indent=4, sort_keys=True)

    def initiate_transfer_burn(self,
                               from_chain,
                               to_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_from = self._connect_aergo(from_chain)

        burner_account = aergo_from.new_account(private_key=priv_key)

        if sender is None:
            # minted token currently doesnt support delegated burn
            sender = burner_account.address.__str__()
        if receiver is None:
            receiver = sender

        bridge_from = self._config_data[from_chain]['bridges'][to_chain]
        token_pegged = self._config_data[to_chain]['tokens'][asset_name]['pegs'][from_chain]

        print("\n\n------ Burn {}-----------".format(asset_name))
        burn_height = burn(aergo_from, sender, receiver, amount,
                           token_pegged, bridge_from)

        # remaining balance on sidechain
        token_pegged = self._config_data[to_chain]['tokens'][asset_name]['pegs'][from_chain]
        balance = self.get_balance(sender, asset_addr=token_pegged,
                                   aergo=aergo_from)
        print("Remaining {} balance on sidechain after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()

        return burn_height

    def finalize_transfer_unlock(self,
                                 burn_height,
                                 from_chain,
                                 to_chain,
                                 asset_name,
                                 receiver=None,
                                 priv_key=None):
        # NOTE anybody can unlock so sender is not necessary
        # amount to unlock is the difference between total burn and
        # already unlocked amount
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_to = self._connect_aergo(to_chain)
        aergo_from = self._connect_aergo(from_chain)
        aergo_to.new_account(private_key=priv_key)
        unlocker_account = aergo_to.new_account(private_key=priv_key)
        if receiver is None:
            receiver = unlocker_account.address.__str__()

        bridge_to = self._config_data[to_chain]['bridges'][from_chain]
        bridge_from = self._config_data[from_chain]['bridges'][to_chain]

        # TODO store t_anchor and t_final for that bridge in config.json. if it
        # doesnt exist, only then query to contract and store it for later
        # store addr, t_anchor, t_final in bridge in confog.json
        print("\n------ Wait finalisation and get burn proof -----------")
        asset_address = self._config_data[to_chain]['tokens'][asset_name]['addr']
        t_anchor, t_final = self.get_bridge_tempo(aergo_to, bridge_to)
        burn_proof = build_burn_proof(aergo_to, aergo_from, receiver,
                                      bridge_to, bridge_from, burn_height,
                                      asset_address, t_anchor, t_final)

        print("\n\n------ Unlock {} on origin blockchain -----------"
              .format(asset_name))
        balance = self.get_balance(receiver, asset_name=asset_name,
                                   asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination before transfer: {}"
              .format(asset_name, balance/10**18))

        unlock(aergo_to, receiver, burn_proof, asset_address, bridge_to)

        # new balance on origin
        balance = self.get_balance(receiver, asset_name=asset_name,
                                   asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination before transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_to.disconnect()
        aergo_from.disconnect()


if __name__ == '__main__':

    selection = 1

    with open("./config.json", "r") as f:
        config_data = json.load(f)
    wallet = Wallet(config_data)

    if selection == 0:
        amount = 1*10**18
        wallet.transfer_to_sidechain('mainnet',
                                    'sidechain2',
                                    'aergo',
                                    amount)
        wallet.transfer_from_sidechain('sidechain2',
                                    'mainnet',
                                    'aergo',
                                    amount)
    elif selection == 1:
        with open("./contracts/token_bytecode.txt", "r") as f:
            payload_str = f.read()[:-1]
        total_supply = 500*10**6*10**18
        wallet.deploy_token(payload_str, "token2", total_supply)

