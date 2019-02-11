import json

import aergo.herapy as herapy

from transfer_to_sidechain import lock_aer, lock_token, build_lock_proof, mint
from transfer_from_sidechain import burn, build_burn_proof, unlock

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

    def get_balance(aergo, asset_name, address):
        pass

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
        pass

    def sign_transfer():
        # signs a transfer to be given to a 3rd party
        pass

    # TODO create a tx broadcaster that calls signed transfer,
    # lock or burn with a signature. gRPC with params arguments

    def deploy_token(asset_name, total_supply, receiver=None, priv_key=None):
        pass

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
                                    asset_name, amount, sender,
                                    receiver, priv_key)

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
                                      asset_name, amount, sender,
                                      receiver, priv_key)

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
            # TODO pass amount
            lock_height = lock_aer(aergo_from, sender, receiver, bridge_from)
        else:
            lock_height = lock_token(aergo_from, sender, receiver, bridge_from,
                                     asset_address)
        # remaining balance on origin
        if asset_name == "aergo":
            # TODO get balance ()
            aergo_from.get_account()
            print("Remaining {} balance on origin after transfer: {}"
                  .format(asset_name, aergo_from.account.balance.aer))
        else:
            origin_balance = aergo_from.query_sc_state(asset_address,
                                                       ["_sv_Balances-" +
                                                        sender
                                                        ])
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("Remaining {} balance on origin after transfer: {}"
                  .format(asset_name, int(balance)/10**18))
        aergo_from.disconnect()
        return lock_height

    def finalize_transfer_mint(self,
                               lock_height,
                               from_chain,
                               to_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        # NOTE anybody can mint so sender is not necessary
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_from = self._connect_aergo(from_chain)
        aergo_to = self._connect_aergo(to_chain)
        aergo_from.new_account(private_key=priv_key)
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
            sidechain_balance = aergo_to.query_sc_state(token_pegged,
                                                        ["_sv_Balances-" +
                                                         receiver
                                                         ])
            balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination before transfer : {}"
                  .format(asset_name, int(balance)/10**18))
        except KeyError:
            # TODO get pegged address from the bridge_to contract
            print("Pegged token unknow by wallet")

        token_pegged = mint(aergo_to, receiver, lock_proof, asset_address,
                            bridge_to)

        # new balance on sidechain
        sidechain_balance = aergo_to.query_sc_state(token_pegged,
                                                    ["_sv_Balances-" +
                                                     receiver,
                                                     ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
        print("{} balance on destination after transfer : {}"
              .format(asset_name, int(balance)/10**18))

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
        burn_height = burn(aergo_from, sender, receiver, bridge_from,
                           token_pegged)

        # remaining balance on sidechain
        token_pegged = self._config_data[to_chain]['tokens'][asset_name]['pegs'][from_chain]
        sidechain_balance = aergo_from.query_sc_state(token_pegged,
                                                      ["_sv_Balances-" +
                                                       sender,
                                                       ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
        print("Remaining {} balance on sidechain after transfer: {}"
              .format(asset_name, int(balance)/10**18))

        aergo_from.disconnect()

        return burn_height

    def finalize_transfer_unlock(self,
                                 burn_height,
                                 from_chain,
                                 to_chain,
                                 asset_name,
                                 amount,
                                 sender=None,
                                 receiver=None,
                                 priv_key=None):
        # NOTE anybody can unlock so sender is not necessary
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo_to = self._connect_aergo(to_chain)
        aergo_from = self._connect_aergo(from_chain)
        aergo_to.new_account(private_key=priv_key)
        unlocker_account = aergo_from.new_account(private_key=priv_key)
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
        if asset_name == "aergo":
            aergo_to.get_account()
            print("{} balance on destination before transfer: {}"
                  .format(asset_name, aergo_to.account.balance.aer))
        else:
            origin_balance = aergo_to.query_sc_state(asset_address,
                                                     ["_sv_Balances-" +
                                                      receiver,
                                                      ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination before transfer: {}"
                  .format(asset_name, int(balance)/10**18))

        unlock(aergo_to, receiver, burn_proof, asset_address, bridge_to)

        # new balance on origin
        if asset_name == "aergo":
            aergo_to.get_account()
            print("{} balance on destination before transfer: {}"
                  .format(asset_name, aergo_to.account.balance.aer))
        else:
            origin_balance = aergo_to.query_sc_state(asset_address,
                                                     ["_sv_Balances-" +
                                                      receiver,
                                                      ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination after transfer: {}"
                  .format(asset_name, int(balance)/10**18))

        aergo_to.disconnect()
        aergo_from.disconnect()


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    wallet = Wallet(config_data)
    wallet.transfer_to_sidechain('mainnet',
                                 'sidechain2',
                                 'aergo',
                                 500)
    wallet.transfer_from_sidechain('sidechain2',
                                   'mainnet',
                                   'aergo',
                                   500)
