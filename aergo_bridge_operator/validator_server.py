import argparse
from concurrent import (
    futures,
)
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
import time

from typing import (
    Optional,
    Dict,
)

import aergo.herapy as herapy

from aergo_bridge_operator.bridge_operator_pb2_grpc import (
    BridgeOperatorServicer,
    add_BridgeOperatorServicer_to_server,
)
from aergo_bridge_operator.bridge_operator_pb2 import (
    Approval,
)
from aergo_bridge_operator.op_utils import (
    query_tempo,
    query_validators,
    query_id,
    query_oracle,
)

_ONE_DAY_IN_SECONDS = 60 * 60 * 24

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_formatter = logging.Formatter(
    '{"level": "%(levelname)s", "time": "%(asctime)s", '
    '"service": "%(funcName)s", "message": %(message)s'
)
stream_formatter = logging.Formatter('%(message)s')


root_dir = os.path.dirname(__file__)
file_handler = logging.FileHandler(root_dir + '/logs/validator.log')
file_handler.setFormatter(file_formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

log_template = \
    '{\"val_index\": %s, \"signed\": %s, \"type\": \"%s\", '\
    '\"destination\": \"%s\"'
success_log_template = log_template + ', \"value\": %s, \"nonce\": %s}'
error_log_template = log_template + ', \"error\": \"%s\"}'


class ValidatorService(BridgeOperatorServicer):
    """Validates anchors for the bridge proposer"""

    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        validator_index: int = 0,
        anchoring_on: bool = False,
        auto_update: bool = False,
        oracle_update: bool = False,
    ) -> None:
        """
        aergo1 is considered to be the mainnet side of the bridge.
        Proposers should set anchor.is_from_mainnet accordingly
        """
        self.config_file_path = config_file_path
        config_data = self.load_config_data()
        self.aergo1 = aergo1
        self.aergo2 = aergo2
        self.hera1 = herapy.Aergo()
        self.hera2 = herapy.Aergo()
        self.anchoring_on = anchoring_on
        self.auto_update = auto_update
        self.oracle_update = oracle_update

        self.hera1.connect(config_data['networks'][aergo1]['ip'])
        self.hera2.connect(config_data['networks'][aergo2]['ip'])

        self.validator_index = validator_index
        self.bridge1 = \
            config_data['networks'][aergo1]['bridges'][aergo2]['addr']
        self.bridge2 = \
            config_data['networks'][aergo2]['bridges'][aergo1]['addr']
        self.oracle1 = \
            config_data['networks'][aergo1]['bridges'][aergo2]['oracle']
        self.oracle2 = \
            config_data['networks'][aergo2]['bridges'][aergo1]['oracle']
        self.id1 = query_id(self.hera1, self.oracle1)
        self.id2 = query_id(self.hera2, self.oracle2)

        # check validators are correct
        validators1 = query_validators(self.hera1, self.oracle1)
        validators2 = query_validators(self.hera2, self.oracle2)
        assert validators1 == validators2, \
            "Validators should be the same on both sides of bridge"
        logger.info("\"Bridge validators : %s\"", validators1)

        # get the current t_anchor and t_final for both sides of bridge
        t_anchor1, t_final1 = query_tempo(
            self.hera1, self.oracle1, ["_sv__tAnchor", "_sv__tFinal"]
        )
        t_anchor2, t_final2 = query_tempo(
            self.hera2, self.oracle2, ["_sv__tAnchor", "_sv__tFinal"]
        )
        logger.info(
            "\"%s <- %s (t_final=%s) : t_anchor=%s\"", aergo1, aergo2,
            t_final1, t_anchor1
        )
        logger.info(
            "\"%s (t_final=%s) -> %s : t_anchor=%s\"", aergo1, t_final2,
            aergo2, t_anchor2
        )
        if auto_update:
            logger.warning(
                "\"WARNING: This validator will vote for settings update in "
                "config.json\""
            )
            if len(validators1) != len(validators2):
                logger.warning(
                    "\"WARNING: different number of validators on both sides "
                    "of the bridge\""
                )
            if len(config_data['validators']) != len(validators1):
                logger.warning(
                    "\"WARNING: This validator is voting for a new set of %s "
                    "validators\"", aergo1
                )
            if len(config_data['validators']) != len(validators2):
                logger.warning(
                    "\"WARNING: This validator is voting for a new set of %s "
                    "validators\"", aergo2
                )
            for i, validator in enumerate(config_data['validators']):
                try:
                    if validator['addr'] != validators1[i]:
                        logger.warning(
                            "\"WARNING: This validator is voting for a new set"
                            " of %s validators\"", aergo1
                        )
                except IndexError:
                    # new validators index larger than current validators
                    pass
                try:
                    if validator['addr'] != validators2[i]:
                        logger.warning(
                            "\"WARNING: This validator is voting for a new set"
                            " of %s validators\"", aergo2
                        )
                except IndexError:
                    # new validators index larger than current validators
                    pass

            t_anchor1_c = (config_data['networks'][aergo1]
                           ['bridges'][aergo2]['t_anchor'])
            t_final1_c = (config_data['networks'][aergo1]
                          ['bridges'][aergo2]['t_final'])
            t_anchor2_c = (config_data['networks'][aergo2]['bridges']
                           [aergo1]['t_anchor'])
            t_final2_c = (config_data['networks'][aergo2]['bridges']
                          [aergo1]['t_final'])
            if t_anchor1_c != t_anchor1:
                logger.warning(
                    "\"WARNING: This validator is voting to update anchoring"
                    " periode of %s on %s\"", aergo2, aergo1
                )
            if t_final1_c != t_final1:
                logger.warning(
                    "\"WARNING: This validator is voting to update finality "
                    " of %s on %s\"", aergo2, aergo1
                )
            if t_anchor2_c != t_anchor2:
                logger.warning(
                    "\"WARNING: This validator is voting to update anchoring"
                    " periode of %s on %s\"", aergo1, aergo2
                )
            if t_final2_c != t_final2:
                logger.warning(
                    "\"WARNING: This validator is voting to update finality "
                    " of %s on %s\"", aergo1, aergo2
                )

        if privkey_name is None:
            privkey_name = 'validator'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = \
            config_data['wallet'][privkey_name]['priv_key']
        self.hera1.import_account(sender_priv_key, privkey_pwd)
        self.hera2.import_account(sender_priv_key, privkey_pwd)
        self.address = str(self.hera1.account.address)
        logger.info("\"Validator Address: %s\"", self.address)

    def GetAnchorSignature(self, anchor, context):
        """ Verifies the anchors are valid and signes them
            aergo1 and aergo2 must be trusted.
        """
        if not self.anchoring_on:
            return Approval(error="Anchoring not enabled")
        destination = ""
        bridge_id = ""
        if anchor.is_from_mainnet:
            # aergo1 is considered to be mainnet side of bridge
            err_msg = self.is_valid_anchor(
                anchor, self.hera1, self.hera2, self.oracle2)
            destination = self.aergo2
            bridge_id = self.id2
        else:
            err_msg = self.is_valid_anchor(
                anchor, self.hera2, self.hera1, self.oracle1)
            destination = self.aergo1
            bridge_id = self.id1
        if err_msg is not None:
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\u2693 anchor", destination, err_msg
            )
            return Approval(error=err_msg)

        # sign anchor and return approval
        msg = bytes(
            anchor.root + ',' + str(anchor.height)
            + str(anchor.destination_nonce) + bridge_id + "R", 'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        sig = self.hera1.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        logger.info(
            success_log_template, self.validator_index, "true",
            "\u2693 anchor", destination,
            "{{\"root\": \"0x{}\", \"height\": {}}}"
            .format(anchor.root, anchor.height),
            anchor.destination_nonce
        )
        return approval

    def is_valid_anchor(
        self,
        anchor,
        aergo_from: herapy.Aergo,
        aergo_to: herapy.Aergo,
        oracle_to: str,
    ) -> Optional[str]:
        """ An anchor is valid if :
            1- it's height is finalized
            2- it's root for that height is correct.
            3- it's nonce is correct
            4- it's height is higher than previous anchored height + t_anchor
        """
        # 1- get the last block height and check anchor height > LIB
        # lib = best_height - finalized_from
        lib = aergo_from.get_status().consensus_info.status['LibNo']
        if anchor.height > lib:
            return ("anchor height not finalized, got: {}, expected: {}"
                    .format(anchor.height, lib))

        # 2- get blocks state root at origin_height
        # and check equals anchor root
        block = aergo_from.get_block(block_height=int(anchor.height))
        root = block.blocks_root_hash.hex()
        if root != anchor.root:
            return ("root doesn't match height {}, got: {}, expected: {}"
                    .format(lib, anchor.root, root))

        # 3-4 setup
        status = aergo_to.query_sc_state(
            oracle_to, ["_sv__anchorHeight", "_sv__tAnchor", "_sv__nonce"])
        last_merged_height_from, t_anchor, last_nonce_to = \
            [int(proof.value) for proof in status.var_proofs]
        # 3- check merkle bridge nonces are correct
        if last_nonce_to != anchor.destination_nonce:
            return ("anchor nonce invalid, got: {}, expected: {}"
                    .format(anchor.destination_nonce, last_nonce_to))

        # 4- check anchored height comes after the previous one and t_anchor is
        # passed
        if last_merged_height_from + t_anchor > anchor.height:
            return ("anchor height too soon, got: {}, expected: {}"
                    .format(anchor.height, last_merged_height_from + t_anchor))
        return None

    def load_config_data(self) -> Dict:
        with open(self.config_file_path, "r") as f:
            config_data = json.load(f)
        return config_data

    def GetTAnchorSignature(self, tempo_msg, context):
        """Get a vote(signature) from the validator to update the t_anchor
        setting in the Aergo bridge contract

        """
        if not self.auto_update:
            return Approval(error="Setting update not enabled")
        if tempo_msg.is_from_mainnet:
            current_tempo = query_tempo(self.hera2, self.oracle2,
                                        ["_sv__tAnchor"])
            return self.get_tempo(
                self.hera2, self.aergo1, self.aergo2, self.oracle2,
                self.id2, tempo_msg, 't_anchor', "A", current_tempo
            )
        else:
            current_tempo = query_tempo(self.hera1, self.oracle1,
                                        ["_sv__tAnchor"])
            return self.get_tempo(
                self.hera1, self.aergo2, self.aergo1, self.oracle1,
                self.id1, tempo_msg, 't_anchor', "A", current_tempo
            )

    def GetTFinalSignature(self, tempo_msg, context):
        """Get a vote(signature) from the validator to update the t_final
        setting in the Aergo bridge contract

        """
        if not self.auto_update:
            return Approval(error="Setting update not enabled")
        if tempo_msg.is_from_mainnet:
            current_tempo = query_tempo(self.hera2, self.oracle2,
                                        ["_sv__tFinal"])
            return self.get_tempo(
                self.hera2, self.aergo1, self.aergo2, self.oracle2,
                self.id2, tempo_msg, 't_final', "F", current_tempo
            )
        else:
            current_tempo = query_tempo(self.hera1, self.oracle1,
                                        ["_sv__tFinal"])
            return self.get_tempo(
                self.hera1, self.aergo2, self.aergo1, self.oracle1,
                self.id1, tempo_msg, 't_final', "F", current_tempo
            )

    def get_tempo(
        self,
        hera: herapy.Aergo,
        aergo_from: str,
        aergo_to: str,
        oracle_to: str,
        id_to: str,
        tempo_msg,
        tempo_str,
        tempo_id,
        current_tempo,
    ):
        # 1 - check destination nonce is correct
        nonce = int(
            hera.query_sc_state(
                oracle_to, ["_sv__nonce"]).var_proofs[0].value
        )
        if nonce != tempo_msg.destination_nonce:
            err_msg = ("Incorrect Nonce, got: {}, expected: {}"
                       .format(tempo_msg.destination_nonce, nonce))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\u231B " + tempo_str, aergo_to, err_msg
            )
            return Approval(error=err_msg)
        config_data = self.load_config_data()
        tempo = (config_data['networks'][aergo_to]['bridges']
                 [aergo_from][tempo_str])
        # 2 - check new tempo is different from current one to prevent
        # update spamming
        if current_tempo == tempo:
            err_msg = "Not voting for a new {}".format(tempo_str)
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\u231B " + tempo_str, aergo_to, err_msg
            )
            return Approval(error=err_msg)
        # 3 - check tempo matches the one in config
        if tempo != tempo_msg.tempo:
            err_msg = ("Invalid {}, got: {}, expected: {}"
                       .format(tempo_str, tempo_msg.tempo, tempo))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\u231B " + tempo_str, aergo_to, err_msg
            )
            return Approval(error=err_msg)
        # sign anchor and return approval
        msg = bytes(
            str(tempo) + str(nonce) + id_to + tempo_id,
            'utf-8'
        )
        h = hashlib.sha256(msg).digest()
        sig = hera.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        logger.info(
            success_log_template, self.validator_index, "true",
            "\u231B " + tempo_str, aergo_to, tempo_msg.tempo,
            tempo_msg.destination_nonce
        )
        return approval

    def GetValidatorsSignature(self, val_msg, context):
        if not (self.auto_update and self.oracle_update):
            return Approval(error="Oracle validators update not enabled")
        if val_msg.is_from_mainnet:
            return self.get_validators(
                self.hera2, self.oracle2, self.id2, self.aergo2,
                val_msg)
        else:
            return self.get_validators(
                self.hera1, self.oracle1, self.id1, self.aergo2,
                val_msg)

    def get_validators(
        self,
        hera: herapy.Aergo,
        oracle_to: str,
        id_to: str,
        aergo_to,
        val_msg,
    ):
        # 1 - check destination nonce is correct
        nonce = int(
            hera.query_sc_state(
                oracle_to, ["_sv__nonce"]).var_proofs[0].value
        )
        if nonce != val_msg.destination_nonce:
            err_msg = ("Incorrect Nonce, got: {}, expected: {}"
                       .format(val_msg.destination_nonce, nonce))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b validator set", aergo_to, err_msg
            )
            return Approval(error=err_msg)
        config_data = self.load_config_data()
        config_vals = [val['addr'] for val in config_data['validators']]
        # 2 - check new validators are different from current ones to prevent
        # update spamming
        current_validators = query_validators(hera, oracle_to)
        if current_validators == config_vals:
            err_msg = "Not voting for a new validator set"
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b validator set", aergo_to, err_msg
            )
            return Approval(error=err_msg)
        # 3 - check validators are same in config file
        if config_vals != val_msg.validators:
            err_msg = ("Invalid validator set, got: {}, expected: {}"
                       .format(val_msg.validators, config_vals))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b validator set", aergo_to, err_msg
            )
            return Approval(error=err_msg)
        # sign validators
        data = ""
        for val in config_vals:
            data += val
        data += str(nonce) + id_to + "V"
        data_bytes = bytes(data, 'utf-8')
        h = hashlib.sha256(data_bytes).digest()
        sig = hera.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        logger.info(
            success_log_template, self.validator_index, "true",
            "\U0001f58b validator set", aergo_to, val_msg.validators,
            val_msg.destination_nonce
        )
        return approval

    def GetOracleSignature(self, oracle_msg, context):
        if not (self.auto_update and self.oracle_update):
            return Approval(error="Oracle update not enabled")

        if oracle_msg.is_from_mainnet:
            return self.get_oracle(
                self.hera2, self.aergo1, self.aergo2, self.oracle2, self.id2,
                self.bridge2, oracle_msg
            )
        else:
            return self.get_oracle(
                self.hera1, self.aergo2, self.aergo1, self.oracle1, self.id1,
                self.bridge1, oracle_msg)

    def get_oracle(
        self,
        hera: herapy.Aergo,
        aergo_from: str,
        aergo_to: str,
        oracle_to: str,
        id_to: str,
        bridge_to: str,
        oracle_msg
    ):
        """Get a vote(signature) from the validator to update the
        oracle controlling the bridge contract

        """
        # 1 - check destination nonce is correct
        nonce = int(
            hera.query_sc_state(
                oracle_to, ["_sv__nonce"]).var_proofs[0].value
        )
        if nonce != oracle_msg.destination_nonce:
            err_msg = ("Incorrect Nonce, got: {}, expected: {}"
                       .format(oracle_msg.destination_nonce, nonce))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b oracle change", aergo_to, err_msg
            )
            return Approval(error=err_msg)

        config_data = self.load_config_data()
        config_oracle = \
            config_data['networks'][aergo_to]['bridges'][aergo_from]['oracle']
        # 2 - check new oracle is different from current one to prevent
        # update spamming
        current_oracle = query_oracle(hera, bridge_to)
        if current_oracle == config_oracle:
            err_msg = "Not voting for a new oracle"
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b oracle change", aergo_to, err_msg
            )
            return Approval(error=err_msg)
        # 3 - check validators are same in config file
        if config_oracle != oracle_msg.oracle:
            err_msg = ("Invalid oracle, got: {}, expected: {}"
                       .format(oracle_msg.oracle, config_oracle))
            logger.warning(
                error_log_template, self.validator_index, "false",
                "\U0001f58b oracle change", aergo_to, err_msg
            )
            return Approval(error=err_msg)

        # sign validators
        data = oracle_msg.oracle \
            + str(oracle_msg.destination_nonce) + id_to + "O"
        data_bytes = bytes(data, 'utf-8')
        h = hashlib.sha256(data_bytes).digest()
        sig = hera.account.private_key.sign_msg(h)
        approval = Approval(address=self.address, sig=sig)
        logger.info(
            success_log_template, self.validator_index, "true",
            "\U0001f58b oracle change", aergo_to,
            "\"{}\"".format(oracle_msg.oracle),
            oracle_msg.destination_nonce
        )
        return approval


class ValidatorServer:
    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
        validator_index: int = 0,
        anchoring_on: bool = False,
        auto_update: bool = False,
        oracle_update: bool = False,
    ) -> None:
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        add_BridgeOperatorServicer_to_server(
            ValidatorService(
                config_file_path, aergo1, aergo2, privkey_name, privkey_pwd,
                validator_index, anchoring_on, auto_update, oracle_update
            ), self.server
        )
        self.server.add_insecure_port(config_data['validators']
                                      [validator_index]['ip'])
        self.validator_index = validator_index

    def run(self):
        self.server.start()
        logger.info("\"server %s started\"", self.validator_index)
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            logger.info("\"Shutting down validator\"")
            self.shutdown()

    def shutdown(self):
        self.server.stop(0)


def _serve_worker(servers, index):
    servers[index].run()


def _serve_all(config_file_path, aergo1, aergo2,
               privkey_name=None, privkey_pwd=None):
    """ For testing, run all validators in different threads """
    with open(config_file_path, "r") as f:
        config_data = json.load(f)
    validator_indexes = [i for i in range(len(config_data['validators']))]
    servers = [ValidatorServer(config_file_path, aergo1, aergo2,
                               privkey_name, privkey_pwd, index, True, True, True)
               for index in validator_indexes]
    worker = partial(_serve_worker, servers)
    pool = Pool(len(validator_indexes))
    pool.map(worker, validator_indexes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Start a validator between 2 Aergo networks.')
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
        '-i', '--validator_index', type=int, required=True,
        help='Index of the validator in the ordered list of validators')
    parser.add_argument(
        '--privkey_name', type=str, help='Name of account in config file '
        'to sign anchors', required=False)
    parser.add_argument(
        '--anchoring_on', dest='anchoring_on', action='store_true',
        help='Enable anchoring (can be diseabled when wanting to only update '
             'settings)'
    )
    parser.add_argument(
        '--auto_update', dest='auto_update', action='store_true',
        help='Update bridge contract when settings change in config file')
    parser.add_argument(
        '--oracle_update', dest='oracle_update', action='store_true',
        help='Update bridge contract when validators or oracle addr '
             'change in config file'
    )
    parser.add_argument(
        '--local_test', dest='local_test', action='store_true',
        help='Start all validators locally for convenient testing')
    parser.set_defaults(anchoring_on=False)
    parser.set_defaults(auto_update=False)
    parser.set_defaults(oracle_update=False)
    parser.set_defaults(local_test=False)

    args = parser.parse_args()

    if args.local_test:
        _serve_all(args.config_file_path, args.net1, args.net2,
                   privkey_name=args.privkey_name, privkey_pwd='1234')
    else:
        validator = ValidatorServer(
            args.config_file_path, args.net1, args.net2,
            privkey_name=args.privkey_name,
            validator_index=args.validator_index,
            anchoring_on=args.anchoring_on,
            auto_update=args.auto_update,
            oracle_update=False  # diseabled by default for safety
        )
        validator.run()
