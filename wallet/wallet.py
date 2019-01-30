import json

import aergo.herapy as herapy

from transfer_to_sidechain import lock_aer, lock_token, build_lock_proof, mint
from transfer_from_sidechain import burn, build_burn_proof, unlock

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
        # TODO try except
        # TODO user "aergo" for pegged token in config.json
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']

        aergo1 = self._connect_aergo(origin_chain)
        sender_account = aergo1.new_account(private_key=priv_key)

        sender = sender_account.address.__str__()
        receiver = sender
        print("  > Sender Address: ", sender)
        bridge_addr = self._config_data[origin_chain]['bridges'][destination_chain]

        print("\n------ Lock tokens/aer -----------")
        asset_address = self._config_data[origin_chain]['tokens'][asset_name]['addr']
        if asset_name == "aergo":
            # TODO pass amount
            lock_height, success = lock_aer(aergo1, sender, receiver, bridge_addr)
        else:
            lock_height, success = lock_token(aergo1, sender, receiver, bridge_addr,
                                              asset_address)
        # remaining balance on origin
        if asset_name == "aergo":
            aergo1.get_account()
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            origin_balance = aergo1.query_sc_state(asset_address,
                                                ["_sv_Balances-" +
                                                    sender,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)
        aergo1.disconnect()
        # TODO check every function disconnects aergo at the end and after
        # exception caught
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
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']
        aergo1 = self._connect_aergo(origin_chain)
        aergo2 = self._connect_aergo(destination_chain)
        aergo1.new_account(private_key=priv_key)
        receiver_account = aergo2.new_account(private_key=priv_key)
        receiver = receiver_account.address.__str__()

        addr1 = self._config_data[origin_chain]['bridges'][destination_chain]
        addr2 = self._config_data[destination_chain]['bridges'][origin_chain]

        # Get bridge information
        bridge_info = aergo2.query_sc_state(addr2,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                             ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")
        print("------ Wait finalisation and get lock proof -----------")
        asset_address = self._config_data[origin_chain]['tokens'][asset_name]['addr']

        lock_proof, success = build_lock_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, lock_height,
                                               asset_address, t_anchor, t_final)
        if not success:
            #TODO use try except
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("\n------ Mint tokens on destination blockchain -----------")
        token_pegged, success = mint(aergo2, receiver, lock_proof,
                                     asset_address, addr2)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        # new balance on sidechain
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   receiver,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Pegged contract address on sidechain :", token_pegged)
        print("Balance on sidechain : ", balance)


        # record mint address in file
        print("------ Store mint address in config.json -----------")
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
        sender_account = aergo2.new_account(private_key=priv_key)
        addr2 = self._config_data[origin_chain]['bridges'][destination_chain]

        sender = sender_account.address.__str__()
        receiver = sender
        print("  > Sender Address: ", sender)
        bridge_addr = self._config_data[origin_chain]['bridges'][destination_chain]
        token_pegged = self._config_data[destination_chain]['tokens'][asset_name]['pegs'][origin_chain]

        # get current balance and nonce
        initial_state = aergo2.query_sc_state(token_pegged,
                                              ["_sv_Balances-" +
                                               sender,
                                               ])
        print("Token address in sidechain : ", token_pegged)
        if not initial_state.account.state_proof.inclusion:
            print("Pegged token doesnt exist in sidechain")
            aergo2.disconnect()
            return
        balance = json.loads(initial_state.var_proofs[0].value)
        print("Token balance on sidechain: ", balance)

        print("\n------ Burn tokens -----------")
        burn_height, success = burn(aergo2, receiver, addr2, token_pegged)
        if not success:
            aergo2.disconnect()
            return
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
        if priv_key == None:
            priv_key = self._config_data['wallet']['priv_key']
        aergo1 = self._connect_aergo(destination_chain)
        aergo2 = self._connect_aergo(origin_chain)
        aergo1.new_account(private_key=priv_key)
        receiver_account = aergo2.new_account(private_key=priv_key)
        receiver = receiver_account.address.__str__()
        sender = receiver

        addr1 = self._config_data[destination_chain]['bridges'][origin_chain]
        addr2 = self._config_data[origin_chain]['bridges'][destination_chain]
        # balance on origin
        if asset_name == "aergo":
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            asset_address = self._config_data[destination_chain]['tokens'][asset_name]['addr']
            origin_balance = aergo1.query_sc_state(asset_address,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)
        bridge_info = aergo1.query_sc_state(addr1,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                             ])
        # TODO store t_anchor and t_final for that bridge in config.json. if it
        # doesnt exist, only then query to contract and store it for later
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")
        print("------ Wait finalisation and get burn proof -----------")
        burn_proof, success = build_burn_proof(aergo1, aergo2, receiver,
                                               addr1, addr2, burn_height,
                                               asset_address, t_anchor, t_final)
        if not success:
            aergo1.disconnect()
            aergo2.disconnect()
            return

        print("\n------ Unlock tokens on origin blockchain -----------")
        if not unlock(aergo1, receiver, burn_proof, asset_address, addr1):
            aergo1.disconnect()
            aergo2.disconnect()
            return

        # remaining balance on sidechain
        token_pegged = self._config_data[destination_chain]['tokens'][asset_name]['pegs'][origin_chain]
        sidechain_balance = aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   sender,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Balance on sidechain: ", balance)

        # new balance on origin
        if asset_name == "aergo":
            aergo1.get_account()
            print("Balance on origin: ", aergo1.account.balance.aer)
        else:
            origin_balance = aergo1.query_sc_state(asset_address,
                                                   ["_sv_Balances-" +
                                                    receiver,
                                                    ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)



if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    wallet = Wallet(config_data)
    wallet.transfer_to_sidechain(
                                'mainnet',
                                'sidechain2',
                                'token1',
                                500)
    wallet.transfer_from_sidechain(
                                'sidechain2',
                                'mainnet',
                                'token1',
                                500)
