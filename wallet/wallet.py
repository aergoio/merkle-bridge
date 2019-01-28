import grpc
import hashlib
import json
import sys
import time

import aergo.herapy as herapy

COMMIT_TIME = 3


class Wallet:
    """ A wallet loads it's private key from config.json and
        implements the functionality to transfer tokens to sidechains
    """

    def __init__(self, config_data, aer=False):
        self._config_data = config_data
        with open("./bridge_operator/bridge_addresses.txt", "r") as f:
            self._addr1 = f.readline()[:52]
            self._addr2 = f.readline()[:52]
        with open("./wallet/token_pegged_address.txt", "r") as f:
            self._token_pegged = f.readline()[:52]
        with open("./wallet/token_address.txt", "r") as f:
            self._token_origin = f.readline()[:52]
        if aer:
            self._token_origin = "aergo"

        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(self._config_data['aergo1']['ip'])
        self._aergo2.connect(self._config_data['aergo2']['ip'])

        sender_priv_key1 = self._config_data["wallet"]['priv_key']
        sender_priv_key2 = self._config_data["wallet"]['priv_key']
        sender_account = self._aergo1.new_account(private_key=sender_priv_key1)
        self._aergo2.new_account(private_key=sender_priv_key2)
        self._aergo1.get_account()
        self._aergo2.get_account()

        self._sender = sender_account.address.__str__()
        self._receiver = self._sender
        print("  > Sender Address: ", self._sender)


    def transfer_to_sidechain(self):
        lock_height = self.initiate_transfer_lock()
        self.finalize_transfer_mint(lock_height)

    def transfer_from_sidechain(self):
        burn_height = self.initiate_transfer_burn()
        self.finalize_transfer_unlock(burn_height)

    def initiate_transfer_lock(self, aer=False):
        # Get bridge information
        bridge_info = self._aergo1.query_sc_state(self._addr1,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                             ])
        self._t_anchor, self._t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", self._t_anchor, "s\n",
              "* chain finality periode : ", self._t_final, "s\n")

        print("\n------ Lock tokens/aer -----------")
        if aer:
            lock_height, success = self.lock_aer(self._aergo1, self._sender, self._receiver, self._addr1)
        else:
            lock_height, success = self.lock_token(self._aergo1, self._sender, self._receiver, self._addr1,
                                              self._token_origin)
        if not success:
            self._aergo1.disconnect()
            self._aergo2.disconnect()
        return lock_height

    def finalize_transfer_mint(self, lock_height, aer=False):
        print("------ Wait finalisation and get lock proof -----------")
        lock_proof, success = self.build_lock_proof(self._aergo1, self._aergo2, self._receiver,
                                               self._addr1, self._addr2, lock_height,
                                               self._token_origin, self._t_anchor, self._t_final)
        if not success:
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return

        print("\n------ Mint tokens on destination blockchain -----------")
        token_pegged, success = self.mint(self._aergo2, self._receiver, lock_proof,
                                     self._token_origin, self._addr2)
        if not success:
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return

        # new balance on sidechain
        sidechain_balance = self._aergo2.query_sc_state(token_pegged,
                                                  ["_sv_Balances-" +
                                                   self._receiver,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Pegged contract address on sidechain :", token_pegged)
        print("Balance on sidechain : ", balance)

        # remaining balance on origin
        if aer:
            self._aergo1.get_account()
            print("Balance on origin: ", self._aergo1.account.balance.aer)
        else:
            origin_balance = self._aergo1.query_sc_state(self._token_origin,
                                                ["_sv_Balances-" +
                                                    self._sender,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        # record mint address in file
        with open("./wallet/token_pegged_address.txt", "w") as f:
            f.write(token_pegged)
            f.write("_MINT_TOKEN_1\n")
        self._token_pegged = token_pegged

    def initiate_transfer_burn(self, aer=False):
        # get current balance and nonce
        initial_state = self._aergo2.query_sc_state(self._token_pegged,
                                              ["_sv_Balances-" +
                                               self._sender,
                                               ])
        print("Token address in sidechain : ", self._token_pegged)
        if not initial_state.account.state_proof.inclusion:
            print("Pegged token doesnt exist in sidechain")
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return
        balance = json.loads(initial_state.var_proofs[0].value)
        print("Token balance on sidechain: ", balance)
        # balance on origin
        if aer:
            print("Balance on origin: ", self._aergo1.account.balance.aer)
        else:
            origin_balance = self._aergo1.query_sc_state(self._token_origin,
                                                   ["_sv_Balances-" +
                                                    self._receiver,
                                                    ])
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)

        print("\n------ Burn tokens -----------")
        burn_height, success = self.burn(self._aergo2, self._receiver, self._addr2, self._token_pegged)
        if not success:
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return
        return burn_height

    def finalize_transfer_unlock(self, burn_height, aer=False):
        bridge_info = self._aergo1.query_sc_state(self._addr1,
                                            ["_sv_T_anchor",
                                             "_sv_T_final",
                                             ])
        t_anchor, t_final = [int(item.value) for item in bridge_info.var_proofs]
        print(" * anchoring periode : ", t_anchor, "s\n",
              "* chain finality periode : ", t_final, "s\n")
        print("------ Wait finalisation and get burn proof -----------")
        burn_proof, success = self.build_burn_proof(self._aergo1, self._aergo2, self._receiver,
                                               self._addr1, self._addr2, burn_height,
                                               self._token_origin, t_anchor, t_final)
        if not success:
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return

        print("\n------ Unlock tokens on origin blockchain -----------")
        if not self.unlock(self._aergo1, self._receiver, burn_proof, self._token_origin, self._addr1):
            self._aergo1.disconnect()
            self._aergo2.disconnect()
            return

        # remaining balance on sidechain
        sidechain_balance = self._aergo2.query_sc_state(self._token_pegged,
                                                  ["_sv_Balances-" +
                                                   self._sender,
                                                   ])
        balance = json.loads(sidechain_balance.var_proofs[0].value)
        print("Balance on sidechain: ", balance)

        # new balance on origin
        if aer:
            self._aergo1.get_account()
            print("Balance on origin: ", self._aergo1.account.balance.aer)
        else:
            origin_balance = self._aergo1.query_sc_state(self._token_origin,
                                                   ["_sv_Balances-" +
                                                    self._receiver,
                                                    ])
            # remaining balance on sidechain
            balance = json.loads(origin_balance.var_proofs[0].value)
            print("Balance on origin: ", balance)




    def lock_aer(self, aergo1, sender, receiver, addr1):
        print("Balance on origin", aergo1.account.balance.aer)
        value = 8*10**18
        print("Transfering", value, "aer...")
        tx, result = aergo1.call_sc(addr1, "lock",
                                    args=[receiver, str(value), "aergo"],
                                    amount=value)
        time.sleep(COMMIT_TIME)
        # Record lock height
        _, lock_height = aergo1.get_blockchain_status()
        # Check lock success
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            return None, False
        print("Lock success : ", result.detail)
        return lock_height, True


    def lock_token(self, aergo1, sender, receiver, addr1, token_origin):
        # get current balance and nonce
        initial_state = aergo1.query_sc_state(token_origin,
                                            ["_sv_Balances-" +
                                            sender,
                                            "_sv_Nonces-" +
                                            sender,
                                            "_sv_ContractID"
                                            ])
        balance_p, nonce_p, contractID_p = [item.value for item in initial_state.var_proofs]
        balance = int(json.loads(balance_p)["_bignum"])
        try:
            nonce = int(nonce_p)
        except ValueError:
            nonce = 0
        print("Token address : ", token_origin)
        print("Balance on origin: ", balance/10**18)

        # make a signed transfer of 8 tokens
        value = 8*10**18
        fee = 0
        deadline = 0
        contractID = str(contractID_p[1:-1], 'utf-8')
        msg = bytes(addr1 + str(value) + str(nonce) + str(fee) +
                    str(deadline) + contractID, 'utf-8')
        h = hashlib.sha256(msg).digest()
        sig = aergo1.account.private_key.sign_msg(h).hex()

        # lock and check block height of lock tx
        print("Transfering", value/10**18, "tokens...")
        tx, result = aergo1.call_sc(addr1, "lock",
                                    args=[receiver, str(value),
                                        token_origin, nonce, sig])
        time.sleep(COMMIT_TIME)
        # Record lock height
        _, lock_height = aergo1.get_blockchain_status()
        # Check lock success
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            return None, False
        print("Lock success : ", result.detail)
        return lock_height, True


    def build_lock_proof(self, aergo1, aergo2, receiver, addr1, addr2, lock_height,
                        token_origin, t_anchor, t_final):
        # check current merged height at destination
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        merged_height2 = int(height_proof_2.var_proofs[0].value)
        print("last merged height at destination :", merged_height2)
        # wait t_final
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final)
        # check last merged height
        height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
        last_merged_height2 = int(height_proof_2.var_proofs[0].value)
        # waite for anchor containing our transfer
        sys.stdout.write("waiting new anchor ")
        while last_merged_height2 < lock_height:
            sys.stdout.flush()
            sys.stdout.write(". ")
            time.sleep(t_anchor/4)
            height_proof_2 = aergo2.query_sc_state(addr2, ["_sv_Height"])
            last_merged_height2 = int(height_proof_2.var_proofs[0].value)
            # TODO do this with events when available
        # get inclusion proof of lock in last merged block
        merge_block1 = aergo1.get_block(block_height=last_merged_height2)
        account_ref = receiver + token_origin
        lock_proof = aergo1.query_sc_state(addr1, ["_sv_Locks-" + account_ref],
                                        root=merge_block1.blocks_root_hash,
                                        compressed=False)
        if not lock_proof.verify_proof(merge_block1.blocks_root_hash):
            print("Unable to verify lock proof")
            return None, False
        return lock_proof, True


    def mint(self, aergo2, receiver, lock_proof, token_origin, addr2):
        balance = lock_proof.var_proofs[0].value.decode('utf-8')[1:-1]
        auditPath = lock_proof.var_proofs[0].auditPath
        ap = [node.hex() for node in auditPath]
        # call mint on aergo2 with the lock proof from aergo1
        tx, result = aergo2.call_sc(addr2, "mint",
                                    args=[receiver, balance,
                                        token_origin, ap])
        time.sleep(COMMIT_TIME)
        result = aergo2.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            return None, False
        print("Mint success on sidechain : ", result.detail)

        self._token_pegged = json.loads(result.detail)[0]
        return self._token_pegged, True


    def burn(self, aergo2, receiver, addr2, token_pegged):
        # lock and check block height of lock tx
        value = 8*10**18
        print("Transfering", value/10**18, "tokens...")
        tx, result = aergo2.call_sc(addr2, "burn",
                                    args=[receiver, str(value), token_pegged])
        time.sleep(COMMIT_TIME)
        # Record burn height
        _, burn_height = aergo2.get_blockchain_status()
        # Check burn success
        result = aergo2.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            return None, False
        print("Burn success : ", result.detail)
        return burn_height, True


    def build_burn_proof(self, aergo1, aergo2, receiver, addr1, addr2, burn_height,
                        token_origin, t_anchor, t_final):
        # check current merged height at destination
        height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
        merged_height1 = int(height_proof_1.var_proofs[0].value)
        print("last merged height at destination :", merged_height1)
        # wait t_final
        print("waiting finalisation :", t_final-COMMIT_TIME, "s...")
        time.sleep(t_final)
        # check last merged height
        height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
        last_merged_height1 = int(height_proof_1.var_proofs[0].value)
        # waite for anchor containing our transfer
        sys.stdout.write("waiting new anchor ")
        while last_merged_height1 < burn_height:
            sys.stdout.flush()
            sys.stdout.write(". ")
            time.sleep(t_anchor/4)
            height_proof_1 = aergo1.query_sc_state(addr1, ["_sv_Height"])
            last_merged_height1 = int(height_proof_1.var_proofs[0].value)
            # TODO do this with events when available
        # get inclusion proof of lock in last merged block
        merge_block2 = aergo2.get_block(block_height=last_merged_height1)
        account_ref = receiver + token_origin
        burn_proof = aergo2.query_sc_state(addr2, ["_sv_Burns-" + account_ref],
                                        root=merge_block2.blocks_root_hash,
                                        compressed=False)
        if not burn_proof.verify_proof(merge_block2.blocks_root_hash):
            print("Unable to verify burn proof")
            return None, False
        return burn_proof, True


    def unlock(self, aergo1, receiver, burn_proof, token_origin, addr1):
        balance = burn_proof.var_proofs[0].value.decode('utf-8')[1:-1]
        auditPath = burn_proof.var_proofs[0].auditPath
        ap = [node.hex() for node in auditPath]
        # call mint on aergo2 with the lock proof from aergo1
        tx, result = aergo1.call_sc(addr1, "unlock",
                                    args=[receiver, balance,
                                        token_origin, ap])
        time.sleep(COMMIT_TIME)
        result = aergo1.get_tx_result(tx.tx_hash)
        if result.status != herapy.SmartcontractStatus.SUCCESS:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result.contract_address, result.status, result.detail))
            return False

        print("Unlock success on origin : ", result.detail)
        return True



