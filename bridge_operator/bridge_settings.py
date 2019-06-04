from getpass import getpass
import hashlib
import time

from typing import (
    Tuple,
    List,
    Union,
    Dict,
)

import aergo.herapy as herapy
from aergo.herapy.utils.signature import (
    verify_sig,
)

from bridge_operator.op_utils import (
    query_tempo,
    query_validators,
)

COMMIT_TIME = 3


class ValidatorMajorityError(Exception):
    pass


class TxError(Exception):
    pass


class BridgeSettingsManager:
    def __init__(self, old_config_data: Dict):
        self._config_data = old_config_data

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

    def get_aergo(
        self,
        network: str,
        privkey_name: str,
        privkey_pwd: str = None
    ) -> herapy.Aergo:
        exported_privkey = self.config_data('wallet', privkey_name, 'priv_key')
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        aergo = herapy.Aergo()
        aergo.connect(self.config_data(network, 'ip'))
        aergo.import_account(exported_privkey, privkey_pwd)
        return aergo

    def _verify_signatures_single(
        self,
        signers: List[int],
        signatures: List[bytes],
        h: bytes
    ) -> Tuple[List[str], List[int]]:
        """ Verify a single list of signatures for updating one side of
        the bridge
        """
        verified_sigs = []
        verified_signers = []
        for i, index in enumerate(signers):
            validator_addr = self.config_data('validators', index, 'addr')
            if verify_sig(h, signatures[i], validator_addr):
                verified_sigs.append('0x' + signatures[i].hex())
                verified_signers.append(index)
        total_validators = len(self.config_data('validators'))
        if 3 * len(verified_sigs) < 2 * total_validators:
            raise ValidatorMajorityError()
        # slice 2/3 of total validators
        two_thirds = ((total_validators * 2) // 3
                      + ((total_validators * 2) % 3 > 0))
        return verified_sigs[:two_thirds], verified_signers[:two_thirds]

    def _verify_signatures_double(
        self,
        signers: List[int],
        signatures1: List[bytes],
        signatures2: List[bytes],
        h1: bytes,
        h2: bytes
    ) -> Tuple[List[str], List[str], List[int]]:
        """ Verify 2 lists of signatures for updating both sides
        of the bridge.
        """
        verified_sigs1 = []
        verified_sigs2 = []
        verified_signers = []
        for i, index in enumerate(signers):
            validator_addr = self.config_data('validators', index, 'addr')

            if verify_sig(h1, signatures1[i], validator_addr) and \
                verify_sig(h2, signatures2[i], validator_addr):

                verified_sigs1.append('0x' + signatures1[i].hex())
                verified_sigs2.append('0x' + signatures2[i].hex())
                verified_signers.append(index)
        total_validators = len(self.config_data('validators'))
        if 3 * len(verified_sigs1) < 2 * total_validators:
            raise ValidatorMajorityError()
        # slice 2/3 of total validators
        two_thirds = ((total_validators * 2) // 3
                      + ((total_validators * 2) % 3 > 0))
        return (verified_sigs1[:two_thirds],
                verified_sigs2[:two_thirds],
                verified_signers[:two_thirds])

    def get_validators(
        self,
        network1: str,
        network2: str
    ) -> Tuple[List[str], List[str]]:
        """ Query the validators on both sides of the bridge : both lists should
        be the same.
        """
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()
        aergo1.connect(self.config_data(network1, 'ip'))
        aergo2.connect(self.config_data(network2, 'ip'))
        bridge1 = self.config_data(network1, 'bridges', network2, 'addr')
        bridge2 = self.config_data(network2, 'bridges', network1, 'addr')
        validators1 = query_validators(aergo1, bridge1)
        validators2 = query_validators(aergo2, bridge2)
        assert validators1 == validators2, "Validators should be the same"
        return validators1, validators2

    def get_t_anchor(
        self,
        network_from: str,
        network_to: str
    ) -> int:
        """ Query the anchoring periode of network_from onto network_to."""
        return self.get_tempo(network_from, network_to, "_sv_T_anchor")[0]

    def get_t_final(
        self,
        network_from: str,
        network_to: str
    ) -> int:
        """ Query when network_from should be considered final by validators
        before it can be anchored on network_to
        """
        return self.get_tempo(network_from, network_to, "_sv_T_final")[0]

    def get_tempo(
        self,
        network_from: str,
        network_to: str,
        tempo: str = None
    ) -> List[int]:
        """ Query t_final or t_achor depending on the tempo argument."""
        if tempo is None:
            args = ["_sv_T_anchor", "_sv_T_final"]
        else:
            args = [tempo]
        aergo = herapy.Aergo()
        aergo.connect(self.config_data(network_to, 'ip'))
        bridge = self.config_data(network_to, 'bridges', network_from, 'addr')
        result = query_tempo(aergo, bridge, args)
        return result

    def sign_t_anchor(
        self,
        t_anchor: int,
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> bytes:
        """Sign a new anchor periode for network_from -> network_to bridge"""
        return self._sign_tempo(t_anchor, "A", network_from, network_to,
                                privkey_name, privkey_pwd)

    def sign_t_final(
        self,
        t_final: int,
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> bytes:
        """ Sign a new finality of network_from for
        network_from -> network_to bridge.
        """
        return self._sign_tempo(t_final, "F", network_from, network_to,
                                privkey_name, privkey_pwd)

    @staticmethod
    def _tempo_digest(
        tempo: int,
        letter: str,
        bridge_addr: str,
        bridge_id: str,
        aergo: herapy.Aergo
    ) -> bytes:
        """ Construct the digest message with the bridge update nonce to be
        signed by the validator for a t_anchor or t_final update.
        """
        # get bridge nonce
        current_nonce = aergo.query_sc_state(bridge_addr, ["_sv_Nonce"])
        current_nonce = int(current_nonce.var_proofs[0].value)
        data = str(tempo) + ',' + str(current_nonce) + ',' + bridge_id + letter
        data_bytes = bytes(data, 'utf-8')
        return hashlib.sha256(data_bytes).digest()

    def _sign_tempo(
        self,
        tempo: int,
        letter: str,
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> bytes:
        """ Sign an update of t_final or t_anchor."""
        if privkey_name is None:
            privkey_name = 'validator'
        aergo = self.get_aergo(network_to, privkey_name, privkey_pwd)
        bridge_addr = self.config_data(network_to, 'bridges', network_from,
                                       'addr')
        bridge_id = self.config_data(network_to, 'bridges', network_from,
                                     'id')
        h = self._tempo_digest(tempo, letter, bridge_addr, bridge_id, aergo)
        sig = aergo.account.private_key.sign_msg(h)
        return sig

    def update_t_anchor(
        self,
        t_anchor: int,
        signers: List[int],
        sigs: List[bytes],
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        """Update the anchoring periode of network_from -> network_to bridge"""
        return self._update_tempo("update_t_anchor", "A", t_anchor, signers,
                                  sigs, network_from, network_to,
                                  privkey_name, privkey_pwd)

    def update_t_final(
        self,
        t_final: int,
        signers: List[int],
        sigs: List[bytes],
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        """Update the finality of network_from for the
        network_from -> network_to bridge
        """
        return self._update_tempo("update_t_final", "F", t_final, signers,
                                  sigs, network_from, network_to,
                                  privkey_name, privkey_pwd)

    def _update_tempo(
        self,
        function: str,
        letter: str,
        tempo: int,
        signers: List[int],
        sigs: List[bytes],
        network_from: str,
        network_to: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        """ Verify the validator signatures before updating the t_anchor or
        t_final of the bridge.
        """
        if privkey_name is None:
            privkey_name = 'proposer'
        aergo = self.get_aergo(network_to, privkey_name, privkey_pwd)
        bridge_addr = self.config_data(network_to, 'bridges', network_from,
                                       'addr')
        bridge_id = self.config_data(network_to, 'bridges', network_from, 'id')
        h = self._tempo_digest(tempo, letter, bridge_addr, bridge_id, aergo)

        # verify signatures and keep only 2/3
        all_sigs = self._verify_signatures_single(signers, sigs, h)
        verified_sigs, verified_signers = all_sigs
        # update tempo on network_to
        tx_hash = self._update_tempo_tx(aergo, bridge_addr, function, tempo,
                                        verified_signers, verified_sigs)
        time.sleep(COMMIT_TIME)
        result = aergo.get_tx_result(tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            raise TxError("{} Tx execution failed : {}"
                          .format(function, result))

        print("\nSuccess {} on {}"
              .format(function, network_to))

    @staticmethod
    def _update_tempo_tx(
        aergo: herapy.Aergo,
        bridge_address: str,
        function: str,
        tempo: int,
        signers: List[int],
        signatures: List[str]
    ) -> herapy.obj.tx_hash.TxHash:
        tx, result = aergo.call_sc(bridge_address, function,
                                   args=[tempo, signers, signatures])
        if result.status != herapy.CommitStatus.TX_OK:
            raise TxError("{} Tx commit failed : {}"
                          .format(function, result))
        return tx.tx_hash

    def sign_new_validators(
        self,
        network1: str,
        network2: str,
        new_validators: List[str],
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> Tuple[bytes, bytes]:
        if privkey_name is None:
            privkey_name = 'validator'
        aergo1 = self.get_aergo(network1, privkey_name, privkey_pwd)
        aergo2 = self.get_aergo(network2, privkey_name, privkey_pwd)
        bridge_addr1 = self.config_data(network1, 'bridges', network2, 'addr')
        bridge_addr2 = self.config_data(network2, 'bridges', network1, 'addr')
        bridge_id1 = self.config_data(network1, 'bridges', network2, 'id')
        bridge_id2 = self.config_data(network2, 'bridges', network1, 'id')

        h1 = self._new_validators_digest(aergo1, bridge_addr1, bridge_id1,
                                         new_validators)
        h2 = self._new_validators_digest(aergo2, bridge_addr2, bridge_id2,
                                         new_validators)
        sig1 = aergo1.account.private_key.sign_msg(h1)
        sig2 = aergo2.account.private_key.sign_msg(h2)
        return sig1, sig2

    @staticmethod
    def _new_validators_digest(
        aergo: herapy.Aergo,
        bridge_addr: str,
        bridge_id: str,
        new_validators: List[str]
    ) -> bytes:
        """ Construct the digest message with the bridge update nonce to be
        signed by the validator for a validator set update.
        """
        # get bridge nonce
        current_nonce = aergo.query_sc_state(bridge_addr, ["_sv_Nonce"])
        current_nonce = int(current_nonce.var_proofs[0].value)
        # format data to be signed
        data = ""
        for val in new_validators:
            data += val + ','
        data += str(current_nonce) + ',' + bridge_id + "V"
        data_bytes = bytes(data, 'utf-8')
        return hashlib.sha256(data_bytes).digest()

    def update_validators(
        self,
        new_validators: List[str],
        signers: List[int],
        signatures1: List[bytes],
        signatures2: List[bytes],
        network1: str,
        network2: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        """ Validators should be the same on both sides of the bridge,
        so update_validators updates both sides.
        """
        if privkey_name is None:
            privkey_name = 'proposer'
        aergo1 = self.get_aergo(network1, privkey_name, privkey_pwd)
        aergo2 = self.get_aergo(network2, privkey_name, privkey_pwd)
        bridge_addr1 = self.config_data(network1, 'bridges', network2, 'addr')
        bridge_addr2 = self.config_data(network2, 'bridges', network1, 'addr')
        bridge_id1 = self.config_data(network1, 'bridges', network2, 'id')
        bridge_id2 = self.config_data(network2, 'bridges', network1, 'id')
        h1 = self._new_validators_digest(aergo1, bridge_addr1, bridge_id1,
                                         new_validators)
        h2 = self._new_validators_digest(aergo2, bridge_addr2, bridge_id2,
                                         new_validators)

        # verify signatures and keep only 2/3
        all_sigs = self._verify_signatures_double(signers, signatures1,
                                                  signatures2, h1, h2)
        verified_sigs1, verified_sigs2, verified_signers = all_sigs

        tx_hash1 = self._update_validators_tx(new_validators, verified_signers,
                                              verified_sigs1, bridge_addr1,
                                              aergo1)
        tx_hash2 = self._update_validators_tx(new_validators, verified_signers,
                                              verified_sigs2, bridge_addr2,
                                              aergo2)

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

    @staticmethod
    def _update_validators_tx(
        new_validators: List[str],
        signers: List[int],
        signatures: List[str],
        bridge_address: str,
        aergo: herapy.Aergo
    ) -> herapy.obj.tx_hash.TxHash:
        tx, result = aergo.call_sc(bridge_address, "update_validators",
                                   args=[new_validators, signers, signatures])
        if result.status != herapy.CommitStatus.TX_OK:
            raise TxError("Set new validators Tx commit failed : {}"
                          .format(result))
        return tx.tx_hash
