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


def query_validators(aergo: herapy.Aergo, bridge: str) -> List[str]:
    nb_validators_q = aergo.query_sc_state(bridge,
                                           ["_sv_Nb_Validators"])
    nb_validators = int(nb_validators_q.var_proofs[0].value)
    args = ["_sv_Validators-" + str(i+1) for i in range(nb_validators)]
    validators_q = aergo.query_sc_state(bridge, args)
    validators = [val.value.decode('utf-8')[1:-1]
                  for val in validators_q.var_proofs]
    return validators
