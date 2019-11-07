import argparse
from functools import (
    partial,
)
from getpass import getpass
import grpc
import hashlib
import json
import logging
from multiprocessing.dummy import (
    Pool,
)
import os
import threading
import time

from typing import (
    Tuple,
    Optional,
    List,
    Any,
    Dict,
)

import aergo.herapy as herapy
from aergo.herapy.utils.signature import (
    verify_sig,
)

from aergo_bridge_operator.bridge_operator_pb2_grpc import (
    BridgeOperatorStub,
)
from aergo_bridge_operator.bridge_operator_pb2 import (
    Anchor,
    NewValidators,
    NewTempo
)
from aergo_bridge_operator.op_utils import (
    query_tempo,
    query_validators,
    query_id,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_formatter = logging.Formatter(
    '{"level": "%(levelname)s", "time": "%(asctime)s", '
    '"thread": "%(threadName)s", '
    '"function": "%(funcName)s", "message": %(message)s'
)
stream_formatter = logging.Formatter('%(threadName)s: %(message)s')


root_dir = os.path.dirname(__file__)
file_handler = logging.FileHandler(root_dir + '/logs/proposer.log')
file_handler.setFormatter(file_formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


class ValidatorMajorityError(Exception):
    pass


class ProposerClient(threading.Thread):
    """The proposer client periodically (every t_anchor) broadcasts
    the finalized trie state root (after lib) of the bridge contract
    on the other side of the bridge after validation by the Validator servers.
    It first checks the last merged height and waits until
    now > lib + t_anchor is reached, then merges the current finalised
    block (lib). Start again after waiting t_anchor.

    Note on config_data:
        - config_data is used to store current validators and their ip when the
          proposer starts. (change validators after the proposer has started)
        - After starting, when users change the config.json, the proposer will
          attempt to gather signatures to reflect the changes.
        - t_anchor value is always taken from the bridge contract
        - validators are taken from the config_data because ip information is
          not stored on chain
        - when a validator set update succeeds, self.config_data is updated
        - if another proposer updates to a new set of validators and the
          proposer doesnt know about it, proposer must be restarted with the
          new current validator set to create new connections to them.
    """

    def __init__(
        self,
        config_file_path: str,
        aergo_from: str,
        aergo_to: str,
        is_from_mainnet: bool,
        privkey_name: str = None,
        privkey_pwd: str = None,
        auto_update: bool = False
    ) -> None:
        threading.Thread.__init__(self, name=aergo_to + " proposer")
        self.config_file_path = config_file_path
        self.config_data = self.load_config_data()
        self.is_from_mainnet = is_from_mainnet
        self.auto_update = auto_update
        self.aergo_from = aergo_from
        self.aergo_to = aergo_to

        self.hera_from = herapy.Aergo()
        self.hera_to = herapy.Aergo()

        self.hera_from.connect(self.config_data['networks'][aergo_from]['ip'])
        self.hera_to.connect(self.config_data['networks'][aergo_to]['ip'])

        self.bridge_from = \
            (self.config_data['networks'][aergo_from]['bridges'][aergo_to]
             ['addr'])
        self.bridge_to = \
            (self.config_data['networks'][aergo_to]['bridges'][aergo_from]
             ['addr'])
        self.oracle_to = \
            (self.config_data['networks'][aergo_to]['bridges'][aergo_from]
             ['oracle'])
        self.oracle_to_id = query_id(self.hera_to, self.oracle_to)

        validators = query_validators(self.hera_to, self.oracle_to)
        logger.info("\"%s Validators: %s\"", self.aergo_to, validators)
        # create all channels with validators
        self.channels: List[grpc._channel.Channel] = []
        self.stubs: List[BridgeOperatorStub] = []
        assert len(validators) == len(self.config_data['validators']), \
            "Validators in config file must match bridge validators " \
            "when starting (current validators connection needed to make "\
            "updates).\nExpected validators: {}".format(validators)
        for i, validator in enumerate(self.config_data['validators']):
            assert validators[i] == validator['addr'], \
                "Validators in config file must match bridge validators " \
                "when starting (current validators connection needed to make "\
                "updates).\nExpected validators: {}".format(validators)
            ip = validator['ip']
            channel = grpc.insecure_channel(ip)
            stub = BridgeOperatorStub(channel)
            self.channels.append(channel)
            self.stubs.append(stub)

        self.pool = Pool(len(self.stubs))

        # get the current t_anchor and t_final for both sides of bridge
        self.t_anchor, self.t_final = query_tempo(
            self.hera_to, self.bridge_to, ["_sv__tAnchor", "_sv__tFinal"]
        )
        logger.info(
            "\"%s (t_final=%s) -> %s  : t_anchor=%s\"", aergo_from,
            self.t_final, aergo_to, self.t_anchor
        )

        logger.info("\"Set Sender Account\"")
        if privkey_name is None:
            privkey_name = 'proposer'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = self.config_data['wallet'][privkey_name]['priv_key']
        self.hera_to.import_account(sender_priv_key, privkey_pwd)
        logger.info(
            "\"%s Proposer Address: %s\"", aergo_to,
            self.hera_to.account.address
        )

    def get_anchor_signatures(
        self,
        root: str,
        merge_height: int,
        nonce: int,
    ) -> Tuple[List[str], List[int]]:
        """ Query all validators and gather 2/3 of their signatures. """

        # messages to get signed
        msg_str = root + ',' + str(merge_height) + str(nonce) \
            + self.oracle_to_id + "R"
        msg = bytes(msg_str, 'utf-8')
        h = hashlib.sha256(msg).digest()

        anchor = Anchor(
            is_from_mainnet=self.is_from_mainnet, root=root,
            height=str(merge_height), destination_nonce=str(nonce))

        # get validator signatures and verify sig in worker
        validator_indexes = [i for i in range(len(self.stubs))]
        worker = partial(self.get_signature_worker, "GetAnchorSignature",
                         anchor, h)
        approvals = self.pool.map(worker, validator_indexes)

        sigs, validator_indexes = self.extract_signatures(approvals)

        return sigs, validator_indexes

    def get_signature_worker(
        self,
        rpc_service: str,
        request,
        h: bytes,
        index: int
    ) -> Optional[Any]:
        """ Get a validator's (index) signature and verify it"""
        try:
            approval = getattr(self.stubs[index], rpc_service)(request)
        except grpc.RpcError as e:
            logger.warning(
                "\"%s on [is_from_mainnet=%s]: Failed to connect to validator "
                "%s (RpcError)\"",
                rpc_service, request.is_from_mainnet, index
            )
            logger.warning(e)
            return None
        if approval.error:
            logger.warning(
                "\"%s on [is_from_mainnet=%s]: %s\"", rpc_service,
                request.is_from_mainnet, approval.error
            )
            return None
        if approval.address != self.config_data['validators'][index]['addr']:
            # check nothing is wrong with validator address
            logger.warning(
                "\"Unexpected validator %s address: %s\"", index,
                approval.address
            )
            return None
        # validate signature
        if not verify_sig(h, approval.sig, approval.address):
            logger.warning("\"Invalid signature from validator %s\"", index)
            return None
        return approval

    def extract_signatures(
        self,
        approvals: List[Any]
    ) -> Tuple[List[str], List[int]]:
        """ Convert signatures to hex string and keep 2/3 of them."""
        sigs, validator_indexes = [], []
        for i, approval in enumerate(approvals):
            if approval is not None:
                # convert to hex string for lua
                sigs.append('0x' + approval.sig.hex())
                validator_indexes.append(i+1)
        total_validators = len(self.config_data['validators'])
        if 3 * len(sigs) < 2 * total_validators:
            raise ValidatorMajorityError()
        # slice 2/3 of total validators
        two_thirds = ((total_validators * 2) // 3
                      + ((total_validators * 2) % 3 > 0))
        return sigs[:two_thirds], validator_indexes[:two_thirds]

    def wait_next_anchor(
        self,
        merged_height: int,
    ) -> int:
        """ Wait until t_anchor has passed after merged height.
        Return the next finalized block after t_anchor to be the next anchor
        """
        lib = self.hera_from.get_status().consensus_info.status['LibNo']
        wait = (merged_height + self.t_anchor) - lib + 1
        while wait > 0:
            logger.info(
                "\"\u23F0 waiting new anchor time : %ss ...\"", wait)
            self.monitor_settings_and_sleep(wait)
            # Wait lib > last merged block height + t_anchor
            lib = self.hera_from.get_status().consensus_info.status['LibNo']
            wait = (merged_height + self.t_anchor) - lib + 1
        return lib

    def new_anchor(
        self,
        root: str,
        next_anchor_height: int,
        validator_indexes: List[int],
        sigs: List[str],
    ) -> None:
        """Anchor a new root on chain"""
        tx, result = self.hera_to.call_sc(
            self.oracle_to, "newAnchor",
            args=[root, next_anchor_height, validator_indexes, sigs]
        )
        if result.status != herapy.CommitStatus.TX_OK:
            logger.warning(
                "\"Anchor on aergo Tx commit failed : %s\"", result.json())
            return

        result = self.hera_to.wait_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            logger.warning(
                "\"Anchor failed: already anchored, or invalid "
                "signature: %s\"", result.json()
            )
        else:
            logger.info(
                "\"\u2693 Anchor success, \u23F0 wait until next anchor "
                "time: %ss...\"", self.t_anchor
            )

    def run(
        self,
    ) -> None:
        """ Gathers signatures from validators, verifies them, and if 2/3 majority
        is acquired, set the new anchored root in bridge_to.
        """
        while True:  # anchor a new root
            # Get last merge information
            status = self.hera_to.query_sc_state(self.bridge_to,
                                                 ["_sv__anchorHeight",
                                                  "_sv__anchorRoot",
                                                  "_sv__tAnchor",
                                                  "_sv__tFinal"
                                                  ])
            height_from, root_from, t_anchor, t_final = \
                [proof.value for proof in status.var_proofs]
            merged_height_from = int(height_from)
            self.t_anchor = int(t_anchor)
            self.t_final = int(t_final)
            nonce_to = int(
                self.hera_to.query_sc_state(
                    self.oracle_to, ["_sv__nonce"]).var_proofs[0].value
            )

            logger.info(
                "\"Current %s -> %s \u2693 anchor: "
                "height: %s, root: 0x%s, nonce: %s\"",
                self.aergo_from, self.aergo_to, merged_height_from,
                root_from.decode('utf-8')[1:-1], nonce_to
            )

            # Wait for the next anchor time
            next_anchor_height = self.wait_next_anchor(merged_height_from)
            # Get root of next anchor to broadcast
            block = self.hera_from.get_block(
                block_height=next_anchor_height
            )
            contract = self.hera_from.get_account(
                address=self.bridge_from, proof=True,
                root=block.blocks_root_hash
            )
            root = contract.state_proof.state.storageRoot.hex()
            if len(root) == 0:
                logger.info("\"waiting deployment finalization...\"")
                time.sleep(5)
                continue
            nonce_to = int(
                self.hera_to.query_sc_state(
                    self.oracle_to, ["_sv__nonce"]).var_proofs[0].value
            )

            logger.info(
                "\"\U0001f58b Gathering validator signatures for: "
                "root: 0x%s, height: %s'\"", root, next_anchor_height
            )

            try:
                sigs, validator_indexes = self.get_anchor_signatures(
                    root, next_anchor_height, nonce_to
                )
            except ValidatorMajorityError:
                logger.warning(
                    "\"Failed to gather 2/3 validators signatures, "
                    "\u23F0 waiting for next anchor...\""
                )
                self.monitor_settings_and_sleep(self.t_anchor)
                continue

            # don't broadcast if somebody else already did
            last_merge = self.hera_to.query_sc_state(
                self.bridge_to, ["_sv__anchorHeight"])
            merged_height = int(last_merge.var_proofs[0].value)
            if merged_height + self.t_anchor >= next_anchor_height:
                logger.warning(
                    "\"Not yet anchor time, maybe another proposer already "
                    "anchored\""
                )
                wait = merged_height + self.t_anchor - next_anchor_height
                self.monitor_settings_and_sleep(wait)
                continue

            # Broadcast finalised merge block
            self.new_anchor(root, next_anchor_height, validator_indexes, sigs)

            # Wait t_anchor
            # counting commit time in t_anchor often leads to 'Next anchor not
            # reached exception.
            self.monitor_settings_and_sleep(self.t_anchor)

    def monitor_settings_and_sleep(self, sleeping_time):
        """While sleeping, periodicaly check changes to the config
        file and update settings if necessary. If another
        proposer updated settings it doesnt matter, validators will
        just not give signatures.

        """
        if self.auto_update:
            start = time.time()
            self.monitor_settings()
            while time.time()-start < sleeping_time-10:
                # check the config file every 10 seconds
                time.sleep(10)
                self.monitor_settings()
            remaining = sleeping_time - (time.time() - start)
            if remaining > 0:
                time.sleep(remaining)
        else:
            time.sleep(sleeping_time)

    def monitor_settings(self):
        """Check if a modification of bridge settings is requested by seeing
        if the config file has been changed and try to update the bridge
        contract (gather 2/3 validators signatures).

        """
        config_data = self.load_config_data()
        validators = query_validators(self.hera_to, self.oracle_to)
        t_anchor, t_final = query_tempo(
            self.hera_to, self.bridge_to, ["_sv__tAnchor", "_sv__tFinal"])
        config_validators = [val['addr']
                             for val in config_data['validators']]
        if validators != config_validators:
            logger.info(
                '\"Validator set update requested: %s\"', config_validators)
            if self.update_validators(config_validators):
                self.config_data = config_data
                self.update_validator_connections()
        config_t_anchor = (config_data['networks'][self.aergo_to]['bridges']
                           [self.aergo_from]['t_anchor'])
        if t_anchor != config_t_anchor:
            logger.info(
                '\"Anchoring periode update requested: %s\"', config_t_anchor)
            self.update_t_anchor(config_t_anchor)
        config_t_final = (config_data['networks'][self.aergo_to]['bridges']
                          [self.aergo_from]['t_final'])
        if t_final != config_t_final:
            logger.info('\"Finality update requested: %s\"', config_t_final)
            self.update_t_final(config_t_final)

    def update_validator_connections(self):
        """Update connections to validators after a successful update
        of bridge validators with the validators in the config file.

        """
        self.channels = []
        self.stubs = []
        for validator in self.config_data['validators']:
            ip = validator['ip']
            channel = grpc.insecure_channel(ip)
            stub = BridgeOperatorStub(channel)
            self.channels.append(channel)
            self.stubs.append(stub)

        self.pool = Pool(len(self.stubs))

    def update_validators(self, new_validators):
        """Try to update the validator set with the one in the config file."""
        try:
            sigs, validator_indexes = self.get_new_validators_signatures(
                new_validators)
        except ValidatorMajorityError:
            logger.warning("\"Failed to gather 2/3 validators signatures\"")
            return False
        # broadcast transaction
        return self.set_validators(new_validators, validator_indexes, sigs)

    def set_validators(self, new_validators, validator_indexes, sigs):
        """Update validators on chain"""
        tx, result = self.hera_to.call_sc(
            self.oracle_to, "validatorsUpdate",
            args=[new_validators, validator_indexes, sigs]
        )
        if result.status != herapy.CommitStatus.TX_OK:
            logger.warning(
                "\"Set new validators Tx commit failed : %s\"",
                result.json()
            )
            return False

        result = self.hera_to.wait_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            logger.warning(
                "\"Set new validators failed : nonce already used, or "
                "invalid signature: %s\"", result.json()
            )
            return False
        else:
            logger.info("\"\U0001f58b New validators update success\"")
        return True

    def get_new_validators_signatures(self, validators):
        """Request approvals of validators for the new validator set."""
        nonce = int(
            self.hera_to.query_sc_state(
                self.oracle_to, ["_sv__nonce"]).var_proofs[0].value
        )
        new_validators_msg = NewValidators(
            is_from_mainnet=self.is_from_mainnet, validators=validators,
            destination_nonce=nonce)
        data = ""
        for val in validators:
            data += val
        data += str(nonce) + self.oracle_to_id + "V"
        data_bytes = bytes(data, 'utf-8')
        h = hashlib.sha256(data_bytes).digest()
        # get validator signatures and verify sig in worker
        validator_indexes = [i for i in range(len(self.stubs))]
        worker = partial(
            self.get_signature_worker, "GetValidatorsSignature",
            new_validators_msg, h
        )
        approvals = self.pool.map(worker, validator_indexes)
        sigs, validator_indexes = self.extract_signatures(approvals)
        return sigs, validator_indexes

    def update_t_anchor(self, t_anchor):
        """Try to update the anchoring periode registered in the bridge
        contract.

        """
        try:
            sigs, validator_indexes = self.get_tempo_signatures(
                t_anchor, "GetTAnchorSignature", "A")
        except ValidatorMajorityError:
            logger.warning("\"Failed to gather 2/3 validators signatures\"")
            return
        # broadcast transaction
        self.set_tempo(t_anchor, validator_indexes, sigs, "tAnchorUpdate")

    def set_tempo(
        self,
        t_anchor,
        validator_indexes,
        sigs,
        contract_function
    ) -> bool:
        """Update t_anchor or t_final on chain"""
        tx, result = self.hera_to.call_sc(
            self.oracle_to, contract_function,
            args=[t_anchor, validator_indexes, sigs]
        )
        if result.status != herapy.CommitStatus.TX_OK:
            logger.warning(
                "\"Set %s Tx commit failed : %s\"",
                contract_function, result.json()
            )
            return False

        result = self.hera_to.wait_tx_result(tx.tx_hash)
        if result.status != herapy.TxResultStatus.SUCCESS:
            logger.warning(
                "\"Set %s failed: nonce already used, or invalid "
                "signature: %s\"",
                contract_function, result.json()
            )
            return False
        else:
            logger.info(
                "\"\u231B %s success\"", contract_function)
        return True

    def update_t_final(self, t_final):
        """Try to update the anchoring periode registered in the bridge
        contract.

        """
        try:
            sigs, validator_indexes = self.get_tempo_signatures(
                t_final, "GetTFinalSignature", "F")
        except ValidatorMajorityError:
            logger.warning("\"Failed to gather 2/3 validators signatures\"")
            return
        # broadcast transaction
        self.set_tempo(t_final, validator_indexes, sigs, "tFinalUpdate")

    def get_tempo_signatures(self, tempo, rpc_service, tempo_id):
        """Request approvals of validators for the new t_anchor or t_final."""
        nonce = int(
            self.hera_to.query_sc_state(
                self.oracle_to, ["_sv__nonce"]).var_proofs[0].value
        )
        new_tempo_msg = NewTempo(
            is_from_mainnet=self.is_from_mainnet, tempo=tempo,
            destination_nonce=nonce)
        msg = bytes(
            str(tempo) + str(nonce) + self.oracle_to_id + tempo_id,
            'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        validator_indexes = [i for i in range(len(self.stubs))]
        worker = partial(
            self.get_signature_worker, rpc_service,
            new_tempo_msg, h
        )
        approvals = self.pool.map(worker, validator_indexes)
        sigs, validator_indexes = self.extract_signatures(approvals)
        return sigs, validator_indexes

    def load_config_data(self) -> Dict:
        with open(self.config_file_path, "r") as f:
            config_data = json.load(f)
        return config_data

    def shutdown(self):
        logger.info("\"Shutting down %s proposer\"", self.aergo_to)
        self.hera_from.disconnect()
        self.hera_to.disconnect()
        for channel in self.channels:
            channel.close()


class BridgeProposerClient:
    """ The BridgeProposerClient starts proposers on both sides of the bridge
    """

    def __init__(
        self,
        config_file_path: str,
        aergo_mainnet: str,
        aergo_sidechain: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        auto_update: bool = False
    ) -> None:
        self.t_proposer1 = ProposerClient(
            config_file_path, aergo_sidechain, aergo_mainnet, False,
            privkey_name, privkey_pwd, auto_update
        )
        self.t_proposer2 = ProposerClient(
            config_file_path, aergo_mainnet, aergo_sidechain, True,
            privkey_name, privkey_pwd, auto_update
        )

    def run(self):
        self.t_proposer1.start()
        self.t_proposer2.start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Start a proposer between 2 Aergo networks.')
    # Add arguments
    parser.add_argument(
        '-c', '--config_file_path', type=str, help='Path to config.json',
        required=True)
    parser.add_argument(
        '--net1', type=str, help='Name of Aergo network in config file',
        required=True)
    parser.add_argument(
        '--net2', type=str, help='Name of Aergo network in config file',
        required=True)
    parser.add_argument(
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)
    parser.add_argument(
        '--auto_update', dest='auto_update', action='store_true',
        help='Update bridge contract when settings change in config file')
    parser.add_argument(
        '--local_test', dest='local_test', action='store_true',
        help='Start proposer with password for testing')
    parser.set_defaults(auto_update=False)
    parser.set_defaults(local_test=False)

    args = parser.parse_args()
    if args.local_test:
        proposer = BridgeProposerClient(
            args.config_file_path, args.net1, args.net2,
            privkey_name=args.privkey_name, privkey_pwd='1234',
            auto_update=args.auto_update
        )
        proposer.run()
    else:
        proposer = BridgeProposerClient(
            args.config_file_path, args.net1, args.net2,
            privkey_name=args.privkey_name, auto_update=args.auto_update
        )
        proposer.run()
