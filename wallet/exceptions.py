class TxError(Exception):
    pass


class InvalidMerkleProofError(Exception):
    pass


class UnknownContractError(Exception):
    pass


class InvalidArgumentsError(Exception):
    pass


class InsufficientBalanceError(Exception):
    pass


class BroadcasterError(Exception):
    pass
