from concurrent import (
    futures,
)
from getpass import getpass
import grpc
import json
import time
from typing import (
    Dict,
    Tuple,
    Union,
    List,
)

import aergo.herapy as herapy

from broadcaster.broadcaster_pb2_grpc import (
    BroadcasterServicer,
    add_BroadcasterServicer_to_server,
)
from broadcaster.broadcaster_pb2 import (
    ExecutionStatus,
)

from bridge_operator.op_utils import (
    query_tempo,
)
from wallet.wallet_utils import (
    verify_signed_transfer,
    transfer,
)
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
from wallet.exceptions import (
    InvalidMerkleProofError,
    TxError,
)

COMMIT_TIME = 3
_ONE_DAY_IN_SECONDS = 60 * 60 * 24


class BroadcasterService(BroadcasterServicer):
    """ Verifies a signed transfer and broadcasts it """

    def __init__(
        self,
        config_data: Dict,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None
    ) -> None:
        """
        aergo1 is considered to be the mainnet side of the bridge.
        """
        self._config_data = config_data
        self.aergo1 = aergo1
        self.aergo2 = aergo2
        self._aergo1 = herapy.Aergo()
        self._aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        self._aergo1.connect(config_data[aergo1]['ip'])
        self._aergo2.connect(config_data[aergo2]['ip'])

        self._addr1 = config_data[aergo1]['bridges'][aergo2]['addr']
        self._addr2 = config_data[aergo2]['bridges'][aergo1]['addr']

        # get the current t_anchor and t_final for both sides of bridge
        self._t_anchor1, self._t_final1 = query_tempo(
            self._aergo1, self._addr1, ["_sv_T_anchor", "_sv_T_final"]
        )
        self._t_anchor2, self._t_final2 = query_tempo(
            self._aergo2, self._addr2, ["_sv_T_anchor", "_sv_T_final"]
        )
        print("{}             <- {} (t_final={}) : t_anchor={}"
              .format(aergo1, aergo2, self._t_final1, self._t_anchor1))
        print("{} (t_final={}) -> {}              : t_anchor={}"
              .format(aergo1, self._t_final2, aergo2, self._t_anchor2))

        print("------ Set Signer Account -----------")
        if privkey_name is None:
            privkey_name = 'broadcaster'
        if privkey_pwd is None:
            privkey_pwd = getpass("Decrypt exported private key '{}'\n"
                                  "Password: ".format(privkey_name))
        sender_priv_key = \
            config_data['wallet'][privkey_name]['priv_key']
        self._aergo1.import_account(sender_priv_key, privkey_pwd)
        self._aergo2.import_account(sender_priv_key, privkey_pwd)
        self.address = str(self._aergo1.account.address)
        print("  > Broadcaster Address: {}".format(self.address))
        self.fee_price = 0

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

    def unpack_request(
        self, req
    ) -> Tuple[str, str, int, Tuple[int, str, str, int], str, bool]:
        owner = req.owner
        token_name = req.token_name
        amount = int(req.amount)
        signed_transfer = (req.nonce, req.signature, req.fee, req.deadline)
        receiver = req.receiver
        is_pegged = req.is_pegged
        return owner, token_name, amount, signed_transfer, receiver, is_pegged

    def check_fee(self, payed_fee: int) -> bool:
        # TODO use live forex
        # TODO simulate aer gas cost instead of fixed tx_aer_fee
        tx_aer_fee = 10**18
        forex = 1  # get the token/aer exchange rate
        margin = 10**18
        minimum_fee = (tx_aer_fee + margin) * forex
        return False if payed_fee < minimum_fee else True

    def BridgeTransfer(self, request, context):
        owner, token_name, amount, signed_transfer, _, is_pegged = \
            self.unpack_request(request)
        if is_pegged:
            return self.transfer_from_sidechain(
                owner, token_name, amount, signed_transfer
            )
        return self.transfer_to_sidechain(
            owner, token_name, amount, signed_transfer,
        )

    def transfer_to_sidechain(
        self,
        owner: str,
        token_name: str,
        amount: int,
        signed_transfer: Tuple[int, str, str, int]
    ) -> ExecutionStatus:
        print("\n-> Transfer to sidechain")
        result = ExecutionStatus()
        try:
            token_addr = self.config_data(self.aergo1, 'tokens', token_name,
                                          'addr')
        except KeyError:
            err_msg = "Token named '{}' if not suported".format(token_name)
            result.error = err_msg
            print(err_msg)
            return result
        # check fee is enough
        payed_fee = int(signed_transfer[2])
        if not self.check_fee(payed_fee):
            err_msg = "Please pay minimum fee."
            result.error = err_msg
            print(err_msg)
            return result
        # verify signed transfer
        ok, err = verify_signed_transfer(
            owner, self._addr1, token_addr, amount, signed_transfer,
            self._aergo1, 5
        )
        if not ok:
            print(err)
            result.error = err
            return result
        # lock
        try:
            lock_height, tx_hash = lock(
                self._aergo1, self._addr1, owner, amount, token_addr,
                0, self.fee_price, signed_transfer
            )
        except TxError as e:
            result.error = "Failed to lock asset"
            print(e)
            return result
        result.deposit_tx_hash = tx_hash
        time.sleep(self._t_final2 - COMMIT_TIME)
        # mint
        try:
            lock_proof = build_lock_proof(
                self._aergo1, self._aergo2, owner, self._addr1, self._addr2,
                lock_height, token_addr, self._t_anchor2, self._t_final2
            )
        except InvalidMerkleProofError:
            err_msg = "Asset locked but error building merkle proof"
            result.error = err_msg
            print(err_msg)
            return result
        try:
            token_pegged, tx_hash = mint(
                self._aergo2, owner, lock_proof, token_addr, self._addr2, 0,
                self.fee_price
            )
        except TxError as e:
            result.error = "Asset locked but failed to mint"
            print(e)
            return result
        self.config_data(self.aergo1, 'tokens', token_name, 'pegs',
                         self.aergo2, value=token_pegged)
        result.withdraw_tx_hash = tx_hash
        return result

    def transfer_from_sidechain(
        self,
        owner: str,
        token_name: str,
        amount: int,
        signed_transfer: Tuple[int, str, str, int]
    ) -> ExecutionStatus:
        print("\n-> Transfer from sidechain")
        result = ExecutionStatus()
        try:
            token_origin = self.config_data(self.aergo1, 'tokens', token_name,
                                            'addr')
        except KeyError:
            err_msg = "Token named '{}' is not suported".format(token_name)
            result.error = err_msg
            print(err_msg)
            return result
        try:
            token_pegged = self.config_data(self.aergo1, 'tokens', token_name,
                                            'pegs', self.aergo2)
        except KeyError:
            # query pegged token
            query = self._aergo2.query_sc_state(
                self._addr2, ["_sv_BridgeTokens-" + token_origin]
            )
            if not query.var_proofs[0].inclusion:
                err_msg = "Token named '{}' is not suported".format(token_name)
                result.error = err_msg
                print(err_msg)
                return result
            token_pegged = query.var_proofs[0].value[1:-1].decode('utf-8')
            self.config_data(self.aergo1, 'tokens', token_name, 'pegs',
                             self.aergo2, value=token_pegged)

        # verify signed transfer
        ok, err = verify_signed_transfer(
            owner, self._addr2, token_pegged, amount, signed_transfer,
            self._aergo2, 5
        )
        if not ok:
            result.error = err
            print(err)
            return result
        try:
            burn_height, tx_hash = burn(
                self._aergo2, self._addr2, owner, amount, token_pegged, 0,
                self.fee_price, signed_transfer
            )
        except TxError as e:
            result.error = "Failed to burn asset"
            print(e)
            return result
        result.deposit_tx_hash = tx_hash
        time.sleep(self._t_final1 - COMMIT_TIME)
        # burn
        try:
            burn_proof = build_burn_proof(
                self._aergo2, self._aergo1, owner, self._addr2, self._addr1,
                burn_height, token_origin, self._t_anchor1, self._t_final1
            )
        except InvalidMerkleProofError:
            err_msg = "Asset burnt but error building merkle proof"
            result.error = err_msg
            print(err_msg)
            return result
        # unlock
        try:
            tx_hash = unlock(self._aergo1, owner, burn_proof, token_origin,
                             self._addr1, 0, self.fee_price)
        except TxError as e:
            result.error = "Asset burnt but failed to unlock"
            print(e)
            return result
        result.withdraw_tx_hash = tx_hash
        return result

    def SimpleTransfer(self, request, context):
        print("\n-> Simple Transfer")
        result = ExecutionStatus()
        owner, token_name, amount, signed_transfer, to, is_pegged = \
            self.unpack_request(request)
        if is_pegged:
            aergo = self._aergo2
        else:
            aergo = self._aergo1
        try:
            if is_pegged:
                token_addr = self.config_data(
                    self.aergo1, 'tokens', token_name, 'pegs', self.aergo2
                )
            else:
                token_addr = self.config_data(
                    self.aergo1, 'tokens', token_name, 'addr'
                )
        except KeyError:
            err_msg = "Token named '{}' is not suported".format(token_name)
            result.error = err_msg
            print(err_msg)
            return result
        # check fee is enough
        payed_fee = int(signed_transfer[2])
        if not self.check_fee(payed_fee):
            err_msg = "Please pay minimum fee."
            result.error = err_msg
            print(err_msg)
            return result
        # verify signed transfer
        ok, err = verify_signed_transfer(
            owner, to, token_addr, amount, signed_transfer, aergo, 5
        )
        if not ok:
            print(err)
            result.error = err
            return result
        try:
            tx_hash = transfer(amount, to, token_addr, aergo, owner,
                               0, self.fee_price, signed_transfer)
        except TxError as e:
            print(e)
            result.error = "Transfer failed"
            return result
        result.transfer_tx_hash = tx_hash
        return result


class BroadcasterServer:
    def __init__(
        self,
        config_file_path: str,
        aergo1: str,
        aergo2: str,
        privkey_name: str = None,
        privkey_pwd: str = None,
    ) -> None:
        with open(config_file_path, "r") as f:
            config_data = json.load(f)
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_BroadcasterServicer_to_server(
            BroadcasterService(config_data, aergo1, aergo2, privkey_name,
                               privkey_pwd),
            self.server)
        self.server.add_insecure_port(config_data['broadcasters']
                                      [aergo1][aergo2]['ip'])

    def run(self):
        self.server.start()
        print("Broadcaster started")
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            print("\nShutting down validator")
            self.shutdown()

    def shutdown(self):
        self.server.stop(0)


if __name__ == '__main__':
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    broadcaster = BroadcasterServer("./config.json", 'mainnet', 'sidechain2')
    broadcaster.run()
