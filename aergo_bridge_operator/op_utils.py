from typing import (
    List,
)

import aergo.herapy as herapy


def query_tempo(
    aergo: herapy.Aergo,
    bridge: str,
    args: List[str]
) -> List[int]:
    result_q = aergo.query_sc_state(bridge, args)
    result = [int(res.value) for res in result_q.var_proofs]
    return result


def query_validators(aergo: herapy.Aergo, oracle: str) -> List[str]:
    nb_validators_q = aergo.query_sc_state(oracle,
                                           ["_sv__validatorsCount"])
    nb_validators = int(nb_validators_q.var_proofs[0].value)
    args = ["_sv__validators-" + str(i+1) for i in range(nb_validators)]
    validators_q = aergo.query_sc_state(oracle, args)
    validators = [val.value.decode('utf-8')[1:-1]
                  for val in validators_q.var_proofs]
    return validators


def query_id(aergo: herapy.Aergo, oracle: str) -> str:
    id_q = aergo.query_sc_state(oracle, ["_sv__contractId"])
    id = id_q.var_proofs[0].value.decode('utf-8')[1:-1]
    return id


def query_oracle(aergo: herapy.Aergo, bridge: str) -> str:
    oracle_q = aergo.query_sc_state(bridge, ["_sv__oracle"])
    oracle = oracle_q.var_proofs[0].value.decode('utf-8')[1:-1]
    return oracle
