import json

import aergo.herapy as herapy

from transfer_to_sidechain import lock_aer, lock_token, build_lock_proof, mint
from transfer_from_sidechain import burn, build_burn_proof, unlock

from exceptions import *

COMMIT_TIME = 3

#TODO remove make transfer_to_sidechain... from readme and replace with wallet

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

    def deploy_token(asset_name, total_supply, receiver=None, priv_key=None):
        pass

    def transfer_to_sidechain(self,
                              origin_chain,
                              destination_chain,
                              asset_name,
                              amount,
                              sender=None,
                              receiver=None,
                              priv_key=None):
        if priv_key == None:
            priv_key = self._config_data["wallet"]['priv_key']
        lock_height = self.initiate_transfer_lock(origin_chain, destination_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        self.finalize_transfer_mint(lock_height, origin_chain, destination_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)

    def transfer_from_sidechain(self,
                              origin_chain,
                              destination_chain,
                              asset_name,
                              amount,
                              sender=None,
                              receiver=None,
                              priv_key=None):
        if priv_key == None:
            priv_key = self._config_data["wallet"]['priv_key']
        burn_height = self.initiate_transfer_burn(origin_chain, destination_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        self.finalize_transfer_unlock(burn_height, origin_chain, destination_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)

    def initiate_transfer_lock(self,
                               origin_chain,
                               destination_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        # TODO make a new aergo if not already passed as argument != None
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo1 = self._connect_aergo(origin_chain)

        locker_account = aergo1.new_account(private_key=priv_key)
        if sender == None:
            sender = locker_account.address.__str__()
        if receiver == None:
            receiver = sender

        addr1 = self._config_data[origin_chain]['bridges'][destination_chain]

        print("\n\n------ Lock {} -----------".format(asset_name))
        asset_address = self._config_data[origin_chain]['tokens'][asset_name]['addr']
        if asset_name == "aergo":
            # TODO pass amount
            lock_height = lock_aer(aergo1, sender, receiver, addr1)
        else:
            lock_height = lock_token(aergo1, sender, receiver, addr1,
                                              asset_address)
        # remaining balance on origin
        if asset_name == "aergo":
            aergo1.get_account()
            print("Remaining {} balance on origin after transfer: {}".format(asset_name, aergo1.account.balance.aer))
        else:
            origin_balance = aergo1.query_sc_state(asset_address,
                                                ["_sv_Balances-" +
                                                    sender,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("Remaining {} balance on origin after transfer: {}".format(asset_name, int(balance)/10**18))
        aergo1.disconnect()
        return lock_height

    def finalize_transfer_mint(self,
                               lock_height,
                               origin_chain,
                               destination_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        # NOTE anybody can mint so sender is not necessary
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo1 = self._connect_aergo(origin_chain)
        aergo2 = self._connect_aergo(destination_chain)
        aergo1.new_account(private_key=priv_key)
        minter_account = aergo2.new_account(private_key=priv_key)
        if receiver == None:
            receiver = minter_account.address.__str__()

        addr1 = self._config_data[origin_chain]['bridges'][destination_chain]
        addr2 = self._config_data[destination_chain]['bridges'][origin_chain]

        print("\n------ Wait finalisation and get lock proof -----------")
        asset_address = self._config_data[origin_chain]['tokens'][asset_name]['addr']
        t_anchor, t_final = self.get_bridge_tempo(aergo2, addr2)
        lock_proof = build_lock_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, lock_height,
                                               asset_address, t_anchor, t_final)

        print("\n\n------ Mint {} on destination blockchain -----------".format(asset_name))
        try:
            token_pegged = self._config_data[origin_chain]['tokens'][asset_name]['pegs'][destination_chain]
            sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                    ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination before transfer : {}".format(asset_name, int(balance)/10**18))
        except KeyError:
            print("Pegged token not yet know because never transferred by this wallet")

        token_pegged = mint(aergo2, receiver, lock_proof,
                                     asset_address, addr2)

        # new balance on sidechain
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   receiver,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
        print("{} balance on destination after transfer : {}".format(asset_name, int(balance)/10**18))

        aergo1.disconnect()
        aergo2.disconnect()

        # record mint address in file
        print("\n------ Store mint address in config.json -----------")
        self._config_data[origin_chain]['tokens'][asset_name]['pegs'][destination_chain] = token_pegged
        with open("./config.json", "w") as f:
            json.dump(self._config_data, f, indent=4, sort_keys=True)

    def initiate_transfer_burn(self,
                               origin_chain,
                               destination_chain,
                               asset_name,
                               amount,
                               sender=None,
                               receiver=None,
                               priv_key=None):
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo2 = self._connect_aergo(origin_chain)

        burner_account = aergo2.new_account(private_key=priv_key)

        if sender == None:
            # minted token currently doesnt support delegated burn
            sender = burner_account.address.__str__()
        if receiver == None:
            receiver = sender

        addr2 = self._config_data[origin_chain]['bridges'][destination_chain]
        token_pegged = self._config_data[destination_chain]['tokens'][asset_name]['pegs'][origin_chain]


        print("\n\n------ Burn {}-----------".format(asset_name))
        burn_height = burn(aergo2, sender, receiver, addr2, token_pegged)

        # remaining balance on sidechain
        token_pegged = self._config_data[destination_chain]['tokens'][asset_name]['pegs'][origin_chain]
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   sender,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)['_bignum']
        print("Remaining {} balance on sidechain after transfer: {}".format(asset_name, int(balance)/10**18))

        aergo2.disconnect()

        return burn_height

    def finalize_transfer_unlock(self,
                                    burn_height,
                                    origin_chain,
                                    destination_chain,
                                    asset_name,
                                    amount,
                                    sender=None,
                                    receiver=None,
                                    priv_key=None):
        # NOTE anybody can unlock so sender is not necessary
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo1 = self._connect_aergo(destination_chain)
        aergo2 = self._connect_aergo(origin_chain)
        aergo1.new_account(private_key=priv_key)
        unlocker_account = aergo2.new_account(private_key=priv_key)
        if receiver == None:
            receiver = unlocker_account.address.__str__()

        addr1 = self._config_data[destination_chain]['bridges'][origin_chain]
        addr2 = self._config_data[origin_chain]['bridges'][destination_chain]

        # TODO store t_anchor and t_final for that bridge in config.json. if it
        # doesnt exist, only then query to contract and store it for later
        print("\n------ Wait finalisation and get burn proof -----------")
        asset_address = self._config_data[destination_chain]['tokens'][asset_name]['addr']
        t_anchor, t_final = self.get_bridge_tempo(aergo1, addr1)
        burn_proof = build_burn_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, burn_height,
                                               asset_address, t_anchor, t_final)

        print("\n\n------ Unlock {} on origin blockchain -----------".format(asset_name))
        if asset_name == "aergo":
            aergo1.get_account()
            print("{} balance on destination before transfer: {}".format(asset_name, aergo1.account.balance.aer))
        else:
            origin_balance = aergo1.query_sc_state(asset_address,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination before transfer: {}".format(asset_name, int(balance)/10**18))

        unlock(aergo1, receiver, burn_proof, asset_address, addr1)

        # new balance on origin
        if asset_name == "aergo":
            aergo1.get_account()
            print("{} balance on destination before transfer: {}".format(asset_name, aergo1.account.balance.aer))
        else:
            origin_balance = aergo1.query_sc_state(asset_address,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)['_bignum']
            print("{} balance on destination after transfer: {}".format(asset_name, int(balance)/10**18))

        aergo1.disconnect()
        aergo2.disconnect()



if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    wallet = Wallet(config_data)
    wallet.transfer_to_sidechain(
                                'mainnet',
                                'sidechain2',
                                'aergo',
                                500)
    wallet.transfer_from_sidechain(
                                'sidechain2',
                                'mainnet',
                                'aergo',
                                500)
