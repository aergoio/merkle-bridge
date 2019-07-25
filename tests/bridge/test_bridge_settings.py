import time

import aergo.herapy as herapy

from aergo_bridge_operator.op_utils import (
    query_tempo,
    query_validators,
)


def test_tempo_update(wallet):
    auto_tempo_update('mainnet', 'sidechain2', wallet)
    auto_tempo_update('sidechain2', 'mainnet', wallet)


def auto_tempo_update(from_chain, to_chain, wallet):
    hera = herapy.Aergo()
    hera.connect(wallet.config_data('networks', to_chain, 'ip'))
    aergo_bridge = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'addr'
    )
    t_anchor_before = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_anchor'
    )
    t_final_before = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_final'
    )
    t_anchor, t_final = query_tempo(hera, aergo_bridge,
                                    ["_sv_T_anchor", "_sv_T_final"])
    assert t_anchor == t_anchor_before
    assert t_final == t_final_before

    # increase tempo
    nonce_before = int(
        hera.query_sc_state(aergo_bridge, ["_sv_Nonce"]).var_proofs[0].value
    )
    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_anchor',
        value=t_anchor_before + 1
    )
    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_final',
        value=t_final_before + 1
    )
    wallet.save_config()
    nonce = nonce_before
    while nonce <= nonce_before + 2:
        time.sleep(t_anchor_before)
        nonce = int(
            hera.query_sc_state(aergo_bridge, ["_sv_Nonce"])
            .var_proofs[0].value
        )

    t_anchor, t_final = query_tempo(hera, aergo_bridge,
                                    ["_sv_T_anchor", "_sv_T_final"])
    assert t_anchor == t_anchor_before + 1
    assert t_final == t_final_before + 1

    # decrease tempo
    nonce_before = int(
        hera.query_sc_state(aergo_bridge, ["_sv_Nonce"]).var_proofs[0].value
    )
    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_anchor',
        value=t_anchor_before
    )
    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_final',
        value=t_final_before
    )
    wallet.save_config()
    nonce = nonce_before
    while nonce <= nonce_before + 2:
        time.sleep(t_anchor_before)
        nonce = int(
            hera.query_sc_state(aergo_bridge, ["_sv_Nonce"])
            .var_proofs[0].value
        )
    t_anchor, t_final = query_tempo(hera, aergo_bridge,
                                    ["_sv_T_anchor", "_sv_T_final"])
    assert t_anchor == t_anchor_before
    assert t_final == t_final_before


def test_validators_update(wallet):
    auto_update_validators('sidechain2', 'mainnet', wallet)
    auto_update_validators('mainnet', 'sidechain2', wallet)


def auto_update_validators(from_chain, to_chain, wallet):
    hera = herapy.Aergo()
    hera.connect(wallet.config_data('networks', to_chain, 'ip'))
    t_anchor_aergo = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_anchor'
    )
    aergo_bridge = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'addr'
    )
    validators_before = wallet.config_data('validators')
    aergo_validators_before = [val['addr'] for val in validators_before]
    aergo_validators = query_validators(hera, aergo_bridge)
    assert aergo_validators == aergo_validators_before

    # add a validator
    aergo_nonce_before = int(
        hera.query_sc_state(aergo_bridge, ["_sv_Nonce"]).var_proofs[0].value
    )
    new_validators = validators_before + [validators_before[0]]
    wallet.config_data('validators', value=new_validators)

    wallet.save_config()
    # wait for changes to be reflacted
    nonce = aergo_nonce_before
    while nonce <= aergo_nonce_before + 2:
        time.sleep(t_anchor_aergo)
        nonce = int(
            hera.query_sc_state(aergo_bridge, ["_sv_Nonce"])
            .var_proofs[0].value
        )
    aergo_validators = query_validators(hera, aergo_bridge)

    assert aergo_validators == \
        aergo_validators_before + [aergo_validators_before[0]]

    # remove added validator
    aergo_nonce_before = int(
        hera.query_sc_state(aergo_bridge, ["_sv_Nonce"]).var_proofs[0].value
    )
    wallet.config_data('validators', value=new_validators[:-1])
    wallet.save_config()
    # wait for changes to be reflacted
    nonce = aergo_nonce_before
    while nonce <= aergo_nonce_before + 2:
        time.sleep(t_anchor_aergo)
        nonce = int(
            hera.query_sc_state(aergo_bridge, ["_sv_Nonce"])
            .var_proofs[0].value
        )
    aergo_validators = query_validators(hera, aergo_bridge)

    assert aergo_validators == aergo_validators_before
