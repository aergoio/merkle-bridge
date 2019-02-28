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

    def __init__(self, config_data, aer=False):
        self._config_data = config_data

    def _connect_aergo(self, network_name):
        aergo = herapy.Aergo()
        aergo.connect(self._config_data[network_name]['ip'])
        return aergo

    def get_balance(self, account, asset_name=None, asset_addr=None,
                    aergo=None, priv_key=None, network_name=None):
        # TODO if account is None, use default wallet address
        balance = 0
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(priv_key, network_name)
            disconnect_me = True
        if asset_name == "aergo":
            ret_account = aergo.get_account(address=account)
            balance = ret_account.balance
            asset_addr = asset_name
        else:
            if asset_addr is None:
                if asset_name is None or network_name is None:
                    raise InvalidArgumentsError("Provide asset address")
                asset_addr = self._config_data[network_name]['tokens'][asset_name]['addr']
            balance_q = aergo.query_sc_state(asset_addr,
                                             ["_sv_Balances-" +
                                              account
                                              ])
            if balance_q.var_proofs[0].inclusion:
                balance = json.loads(balance_q.var_proofs[0].value)['_bignum']
        if disconnect_me:
            aergo.disconnect()
        return int(balance), asset_addr

    def get_minteable_balance(self, bridge_to, aergo_to, receiver,
                              asset_address_origin, total_Locks=None,
                              bridge_from=None, aergo_from=None):
        return self._bridge_withdrawable_balance("_sv_Locks-", "_sv_Mints-",
                                                 bridge_to, aergo_to, receiver,
                                                 asset_address_origin, total_Deposit=total_Locks,
                                                 bridge_from=bridge_from, aergo_from=aergo_from)

    def get_unlockeable_balance(self, bridge_to, aergo_to, receiver,
                                asset_address_origin, total_Burns=None,
                                bridge_from=None, aergo_from=None):
        return self._bridge_withdrawable_balance("_sv_Burns-", "_sv_Unlocks-",
                                                 bridge_to, aergo_to, receiver,
                                                 asset_address_origin, total_Deposit=total_Burns,
                                                 bridge_from=bridge_from, aergo_from=aergo_from)

    def _bridge_withdrawable_balance(self, deposit_key, withdraw_key,
                                     bridge_to, aergo_to, receiver,
                                     asset_address_origin, total_Deposit=None,
                                     bridge_from=None, aergo_from=None):
        total_withdrawn = 0
        account_ref = receiver + asset_address_origin
        if total_Deposit is None:
            # get the lock proof for the last anchored block on aergo_to
            withdraw_proof = aergo_to.query_sc_state(bridge_to,
                                                     ["_sv_Height",
                                                      withdraw_key + account_ref],
                                                     compressed=False)
            if withdraw_proof.var_proofs[0].inclusion:
                total_withdrawn = int(withdraw_proof.var_proofs[1].value.decode('utf-8')[1:-1])
            last_merged_height_to = int(withdraw_proof.var_proofs[0].value)
            merge_block_from = aergo_from.get_block(block_height=last_merged_height_to)
            deposit_proof = aergo_from.query_sc_state(bridge_from,
                                                      [deposit_key + account_ref],
                                                      root=merge_block_from.blocks_root_hash,
                                                      compressed=False)
            if deposit_proof.var_proofs[0].inclusion:
                total_Deposit = int(deposit_proof.var_proofs[0].value.decode('utf-8')[1:-1])
            else:
                total_Deposit = 0
        else:
            withdraw_proof = aergo_to.query_sc_state(bridge_to,
                                                   [withdraw_key + account_ref],
                                                   compressed=False)
            if withdraw_proof.var_proofs[0].inclusion:
                total_withdrawn = int(withdraw_proof.var_proofs[0].value.decode('utf-8')[1:-1])
        print("\nWithdrawable asset quantity: {} ".format(total_Deposit - total_withdrawn))
        return total_Deposit - total_withdrawn

    def get_bridge_tempo(self, aergo, bridge_address):
        # Get bridge information
        bridge_info = aergo.query_sc_state(bridge_address,
                                           ["_sv_T_anchor",
                                            "_sv_T_final",
                                            ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        return t_anchor, t_final

    def get_aergo(self, priv_key, network_name, skip_state=False):
        if priv_key is None:
            priv_key = self._config_data['wallet']['priv_key']
        if network_name is None:
            raise InvalidArgumentsError("Provide network_name")
        aergo = self._connect_aergo(network_name)
        aergo.new_account(private_key=priv_key, skip_state=skip_state)
        return aergo

    def transfer(self, value, to, asset_name=None, asset_addr=None,
                 aergo=None, priv_key=None, network_name=None):
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(priv_key, network_name)
            disconnect_me = True
        else:
            aergo.get_account()  # get the latest nonce for making tx
        sender = aergo.account.address.__str__()

        balance, asset_addr = self.get_balance(sender, asset_name,
                                               asset_addr, aergo,
                                               network_name=network_name)
        if balance < value:
            raise InsufficientBalanceError("not enough balance")

        if asset_name == "aergo":
            # transfer aer
            tx, result = aergo.send_payload(to_address=to,
                                            amount=value, payload=None)
        else:
            # transfer token
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

    def get_signed_transfer(self, asset_address, value, to, fee=0, deadline=0,
                            aergo=None, priv_key=None, network_name=None):
        # signs a transfer to be given to a 3rd party
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(priv_key, network_name,
                                   skip_state=True)  # state not needed
            disconnect_me = True
        # get current balance and nonce
        sender = aergo.account.address.__str__()
        initial_state = aergo.query_sc_state(asset_address,
                                             ["_sv_Balances-" + sender,
                                              "_sv_Nonces-" + sender,
                                              "_sv_ContractID"
                                              ])
        balance_p, nonce_p, contractID_p = [item.value for item in initial_state.var_proofs]
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

    def deploy_token(self, payload_str, asset_name,
                     total_supply, network_name='mainnet',
                     aergo=None, receiver=None, priv_key=None,
                     path="./config.json"):
        disconnect_me = False
        if aergo is None:
            aergo = self.get_aergo(priv_key, network_name)
            disconnect_me = True
        else:
            aergo.get_account()  # get latest nonce for tx

        if receiver is None:
            receiver = aergo.account.address.__str__()
        print("  > Sender Address: {}".format(receiver))

        sc_address = deploy_token(payload_str, aergo, receiver, total_supply)

        print("------ Store addresse in config.json -----------")
        self._config_data[network_name]['tokens'][asset_name] = {}
        self._config_data[network_name]['tokens'][asset_name]['addr'] = sc_address
        self._config_data[network_name]['tokens'][asset_name]['pegs'] = {}
        self.save_config(path)
        if disconnect_me:
            aergo.disconnect()
        return True

    def transfer_to_sidechain(self,
                              from_chain,
                              to_chain,
                              asset_name,
                              amount,
                              sender=None,
                              receiver=None,
                              priv_key=None,
                              path="./config.json",
                              t_anchor=None,
                              t_final=None):
        if priv_key is None:
            priv_key = self._config_data["wallet"]['priv_key']
        if t_anchor is None:
            t_anchor = self._config_data["t_anchor"]
        if t_final is None:
            t_final = self._config_data["t_final"]
        lock_height = self.initiate_transfer_lock(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final-COMMIT_TIME)

        self.finalize_transfer_mint(from_chain, to_chain, asset_name,
                                    receiver, lock_height, priv_key,
                                    path, t_anchor, t_final)

    def transfer_from_sidechain(self,
                                from_chain,
                                to_chain,
                                asset_name,
                                amount,
                                sender=None,
                                receiver=None,
                                priv_key=None,
                                t_anchor=None,
                                t_final=None):
        if priv_key is None:
            priv_key = self._config_data["wallet"]['priv_key']
        if t_anchor is None:
            t_anchor = self._config_data["t_anchor"]
        if t_final is None:
            t_final = self._config_data["t_final"]
        burn_height = self.initiate_transfer_burn(from_chain, to_chain,
                                                  asset_name, amount, sender,
                                                  receiver, priv_key)
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final-COMMIT_TIME)

        self.finalize_transfer_unlock(from_chain, to_chain, asset_name,
                                      receiver, burn_height, priv_key,
                                      t_anchor, t_final)

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
        balance = 0
        signed_transfer = None
        if asset_name == "aergo":
            balance, _ = self.get_balance(sender, asset_name=asset_name,
                                          asset_addr=asset_address,
                                          aergo=aergo_from)
        else:
            nonce, signature, balance = self.get_signed_transfer(asset_address,
                                                                 amount,
                                                                 bridge_from,
                                                                 aergo=aergo_from)
            signed_transfer = [nonce, signature]
        print("{} balance on origin before transfer: {}"
              .format(asset_name, balance/10**18))
        if balance < amount:
            raise InsufficientBalanceError("not enough balance")

        lock_height = lock(aergo_from, bridge_from,
                           receiver, amount, asset_address,
                           signed_transfer)

        # remaining balance on origin
        balance, _ = self.get_balance(sender, asset_name=asset_name,
                                      asset_addr=asset_address,
                                      aergo=aergo_from)
        print("Remaining {} balance on origin after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_from.disconnect()
        return lock_height

    def finalize_transfer_mint(self,
                               from_chain,
                               to_chain,
                               asset_name,
                               receiver=None,
                               lock_height=0,
                               priv_key=None,
                               path="./config.json",
                               t_anchor=None,
                               t_final=None):
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

        if t_anchor is None or t_final is None:
            t_anchor, t_final = self.get_bridge_tempo(aergo_to, bridge_to)

        print("\n------ Get lock proof -----------")
        asset_address = self._config_data[from_chain]['tokens'][asset_name]['addr']
        lock_proof = build_lock_proof(aergo_from, aergo_to, receiver,
                                      bridge_from, bridge_to, lock_height,
                                      asset_address, t_anchor, t_final)

        total_Locks = int(lock_proof.var_proofs[0].value.decode('utf-8')[1:-1])
        if self.get_minteable_balance(bridge_to, aergo_to, receiver,
                                      asset_address, total_Locks) == 0:
            print("All {} already minted, lock assets on {} first"
                  .format(asset_name, from_chain))
            aergo_from.disconnect()
            aergo_to.disconnect()
            return

        print("\n\n------ Mint {} on destination blockchain -----------"
              .format(asset_name))
        try:
            token_pegged = self._config_data[from_chain]['tokens'][asset_name]['pegs'][to_chain]
            balance, _ = self.get_balance(receiver, asset_addr=token_pegged,
                                          aergo=aergo_to)
            print("{} balance on destination before transfer : {}"
                  .format(asset_name, balance/10**18))
        except KeyError:
            # TODO get pegged address from the bridge_to contract
            print("Pegged token unknow by wallet")

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
        print("\n------ Store mint address in config.json -----------")
        self._config_data[from_chain]['tokens'][asset_name]['pegs'][to_chain] = token_pegged
        self.save_config(path)

    def save_config(self, path):
        with open(path, "w") as f:
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
        token_pegged = self._config_data[to_chain]['tokens'][asset_name]['pegs'][from_chain]
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

    def finalize_transfer_unlock(self,
                                 from_chain,
                                 to_chain,
                                 asset_name,
                                 receiver=None,
                                 burn_height=0,
                                 priv_key=None,
                                 t_anchor=None,
                                 t_final=None):
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

        if t_anchor is None or t_final is None:
            t_anchor, t_final = self.get_bridge_tempo(aergo_to, bridge_to)
            # TODO store t_anchor and t_final for that bridge in config.json. if it
            # doesnt exist, only then query to contract and store it for later
            # store addr, t_anchor, t_final in bridge in confog.json

        print("\n------ Get burn proof -----------")
        asset_address = self._config_data[to_chain]['tokens'][asset_name]['addr']
        burn_proof = build_burn_proof(aergo_to, aergo_from, receiver,
                                      bridge_to, bridge_from, burn_height,
                                      asset_address, t_anchor, t_final)

        total_Burns = int(burn_proof.var_proofs[0].value.decode('utf-8')[1:-1])
        if self.get_unlockeable_balance(bridge_to, aergo_to, receiver,
                                        asset_address, total_Burns) == 0:
            print("All {} already minted, lock assets on {} first"
                  .format(asset_name, from_chain))
            aergo_from.disconnect()
            aergo_to.disconnect()
            return

        print("\n\n------ Unlock {} on origin blockchain -----------"
              .format(asset_name))
        balance, _ = self.get_balance(receiver, asset_name=asset_name,
                                      asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination before transfer: {}"
              .format(asset_name, balance/10**18))

        unlock(aergo_to, receiver, burn_proof, asset_address, bridge_to)

        # new balance on origin
        balance, _ = self.get_balance(receiver, asset_name=asset_name,
                                      asset_addr=asset_address, aergo=aergo_to)
        print("{} balance on destination after transfer: {}"
              .format(asset_name, balance/10**18))

        aergo_to.disconnect()
        aergo_from.disconnect()


if __name__ == '__main__':

    selection = 0

    with open("./config.json", "r") as f:
        config_data = json.load(f)
    wallet = Wallet(config_data)

    if selection == 0:
        amount = 1*10**18
        asset = 'token1'
        wallet.transfer_to_sidechain('mainnet',
                                     'sidechain2',
                                     asset,
                                     amount)
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
        to = config_data['validators'][0]['addr']
        sender = config_data['wallet']['addr']
        asset = 'aergo'
        result = wallet.get_balance(to, asset_name=asset,
                                    network_name='mainnet')
        print('receiver balance before', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    network_name='mainnet')
        print('sender balance before', result)

        wallet.transfer(2, to, asset_name=asset, network_name='mainnet')

        result = wallet.get_balance(to, asset_name=asset,
                                    network_name='mainnet')
        print('receiver balance result', result)
        result = wallet.get_balance(sender, asset_name=asset,
                                    network_name='mainnet')
        print('sender balance after', result)
