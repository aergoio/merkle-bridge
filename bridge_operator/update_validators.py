import hashlib
import json
import time

import aergo.herapy as herapy
from aergo.herapy.utils.signature import (
    verify_sig,
)

COMMIT_TIME = 3


class ValidatorMajorityError(Exception):
    pass


class TxError(Exception):
    pass


class ValidatorsManager:
    def __init__(self, old_config_data):
        self._config_data = old_config_data

    def get_aergo_providers(self, network1, network2, priv_key):
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()
        aergo1.connect(config_data[network1]['ip'])
        aergo2.connect(config_data[network2]['ip'])
        aergo1.new_account(private_key=priv_key)
        aergo2.new_account(private_key=priv_key)
        return aergo1, aergo2

    def sign_t_anchor(self, t_anchor):
        pass

    def sign_t_final(self, t_final):
        pass

    def update_t_anchor(self, data):
        pass

    def update_t_final(self, data):
        pass

    def sign_new_validators(self, network1, network2, new_validators,
                            priv_key=None, validator_index=0):
        if priv_key is None:
            priv_key = self._config_data['validators'][validator_index]['priv_key']
        aergo1, aergo2 = self.get_aergo_providers(network1, network2, priv_key)
        bridge1 = self._config_data[network1]['bridges'][network2]
        bridge2 = self._config_data[network2]['bridges'][network1]

        h1 = self._new_validators_digest(aergo1, bridge1, new_validators)
        h2 = self._new_validators_digest(aergo2, bridge2, new_validators)
        sig1 = aergo1.account.private_key.sign_msg(h1)
        sig2 = aergo2.account.private_key.sign_msg(h2)
        return sig1, sig2

    def _new_validators_digest(self, aergo, bridge, new_validators):
        # get bridge nonce
        current_nonce = aergo.query_sc_state(bridge, ["_sv_Nonce"])
        current_nonce = int(current_nonce.var_proofs[0].value)

        # format data to be signed
        data = ""
        for val in new_validators:
            data += val
        data += str(current_nonce)
        data_bytes = bytes(data, 'utf-8')
        return hashlib.sha256(data_bytes).digest()

    def _verify_signatures(self, signers, signatures1, signatures2, h1, h2):
        verified_sigs1 = []
        verified_sigs2 = []
        verified_signers = []
        for i, index in enumerate(signers):
            validator_addr = self._config_data['validators'][index]['addr']
            if (verify_sig(h1, signatures1[i], validator_addr) and
                verify_sig(h2, signatures2[i], validator_addr)):
                verified_sigs1.append('0x' + signatures1[i].hex())
                verified_sigs2.append('0x' + signatures2[i].hex())
                verified_signers.append(index)
        total_validators = len(self._config_data['validators'])
        if 3 * len(verified_sigs1) < 2 * total_validators:
            raise ValidatorMajorityError()
        # slice 2/3 of total validators
        two_thirds = ((total_validators * 2) // 3
                      + ((total_validators * 2) % 3 > 0))
        return (verified_sigs1[:two_thirds],
                verified_sigs2[:two_thirds],
                verified_signers[:two_thirds])

    def update_validators(self, new_validators, signers,
                          signatures1, signatures2,
                          network1, network2, priv_key=None):
        if priv_key is None:
            priv_key = self._config_data["proposer"]['priv_key']
        aergo1, aergo2 = self.get_aergo_providers(network1, network2, priv_key)
        bridge1 = self._config_data[network1]['bridges'][network2]
        bridge2 = self._config_data[network2]['bridges'][network1]
        h1 = self._new_validators_digest(aergo1, bridge1, new_validators)
        h2 = self._new_validators_digest(aergo2, bridge2, new_validators)

        # verify signatures and keep only 2/3
        all_sigs = self._verify_signatures(signers,
                                           signatures1, signatures2,
                                           h1, h2)
        verified_sigs1, verified_sigs2, verified_signers = all_sigs

        tx_hash1 = self._update_validators_tx(new_validators, verified_signers,
                                              verified_sigs1, bridge1, aergo1)
        tx_hash2 = self._update_validators_tx(new_validators, verified_signers,
                                              verified_sigs2, bridge2, aergo2)

        time.sleep(COMMIT_TIME)
        result1 = aergo1.get_tx_result(tx_hash1)
        result2 = aergo2.get_tx_result(tx_hash2)
        if result1.status != herapy.TxResultStatus.SUCCESS:
            raise TxError("Set new validators Tx execution failed : {}"
                          .format(result1))
        if result2.status != herapy.TxResultStatus.SUCCESS:
            raise TxError("Set new validators Tx execution failed : {}"
                          .format(result2))

        print("\nSuccess validators updated on {} and {}"
              .format(network1, network2))
        print("\nDon't forget to use a new config file with the new " +
              "validators and their ip addresses when restarting the bridge\n")

    def _update_validators_tx(self, new_validators, signers, signatures,
                              bridge_address, aergo):
        tx, result = aergo.call_sc(bridge_address, "new_validators",
                                   args=[new_validators, signers, signatures])
        if result.status != herapy.CommitStatus.TX_OK:
            raise TxError("Set new validators Tx commit failed : {}"
                          .format(result))
        return tx.tx_hash

    def get_validators(self, network1, network2):
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()
        aergo1.connect(config_data[network1]['ip'])
        aergo2.connect(config_data[network2]['ip'])
        bridge1 = self._config_data[network1]['bridges'][network2]
        bridge2 = self._config_data[network2]['bridges'][network1]
        nb_validators_q = aergo1.query_sc_state(bridge1,
                                                ["_sv_Nb_Validators"])
        nb_validators = int(nb_validators_q.var_proofs[0].value)
        args = ["_sv_Validators-" + str(i+1) for i in range(nb_validators)]
        validators_q = aergo1.query_sc_state(bridge1, args)
        validators1 = [val.value for val in validators_q.var_proofs]

        nb_validators_q = aergo2.query_sc_state(bridge2,
                                                ["_sv_Nb_Validators"])
        nb_validators = int(nb_validators_q.var_proofs[0].value)
        args = ["_sv_Validators-" + str(i+1) for i in range(nb_validators)]
        validators_q = aergo2.query_sc_state(bridge2, args)
        validators2 = [val.value for val in validators_q.var_proofs]
        return validators1, validators2


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)

    new_validators = ["AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474"]
    manager = ValidatorsManager(config_data)
    sig1, sig2 = manager.sign_new_validators('mainnet', 'sidechain2',
                                             new_validators)
    manager.update_validators(new_validators,
                              [1, 2],
                              [sig1, sig1],
                              [sig2, sig2],
                              'mainnet', 'sidechain2')
    validators = manager.get_validators('mainnet', 'sidechain2')
    print("increased number of validators to : {}".format(len(validators[0])))
    print(validators)

    with open("./test_config.json", "r") as f:
        test_config_data = json.load(f)
    new_validators = ["AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474"]
    manager = ValidatorsManager(test_config_data)
    sig1, sig2 = manager.sign_new_validators('mainnet', 'sidechain2',
                                             new_validators)
    manager.update_validators(new_validators,
                              [1, 2, 3],
                              [sig1, sig1, sig1],
                              [sig2, sig2, sig2],
                              'mainnet', 'sidechain2')
    validators = manager.get_validators('mainnet', 'sidechain2')
    print("decreased number of validators  to : {}".format(len(validators[0])))
    print(validators)
