import time

import aergo.herapy as herapy

from aergo_bridge_operator.op_utils import (
    query_tempo,
    query_validators,
    query_oracle,
)


def test_tempo_update(wallet):
    auto_tempo_update('mainnet', 'sidechain2', wallet)
    auto_tempo_update('sidechain2', 'mainnet', wallet)


def auto_tempo_update(from_chain, to_chain, wallet):
    hera = herapy.Aergo()
    hera.connect(wallet.config_data('networks', to_chain, 'ip'))
    bridge = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'addr'
    )
    oracle = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'oracle'
    )
    t_anchor_before = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_anchor'
    )
    t_final_before = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 't_final'
    )
    t_anchor, t_final = query_tempo(
        hera, bridge, ["_sv__tAnchor", "_sv__tFinal"])
    assert t_anchor == t_anchor_before
    assert t_final == t_final_before

    # increase tempo
    nonce_before = int(
        hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
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
            hera.query_sc_state(
                oracle, ["_sv__nonce"]).var_proofs[0].value
        )

    t_anchor, t_final = query_tempo(
        hera, bridge, ["_sv__tAnchor", "_sv__tFinal"])
    assert t_anchor == t_anchor_before + 1
    assert t_final == t_final_before + 1

    # decrease tempo
    nonce_before = int(
        hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
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
            hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
        )
    t_anchor, t_final = query_tempo(hera, bridge,
                                    ["_sv__tAnchor", "_sv__tFinal"])
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
    oracle = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'oracle'
    )
    validators_before = wallet.config_data('validators')
    aergo_validators_before = [val['addr'] for val in validators_before]
    aergo_validators = query_validators(hera, oracle)
    assert aergo_validators == aergo_validators_before

    # add a validator
    aergo_nonce_before = int(
        hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
    )
    new_validators = validators_before + [validators_before[0]]
    wallet.config_data('validators', value=new_validators)

    wallet.save_config()
    # wait for changes to be reflacted
    nonce = aergo_nonce_before
    while nonce <= aergo_nonce_before + 2:
        time.sleep(t_anchor_aergo)
        nonce = int(
            hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
        )
    aergo_validators = query_validators(hera, oracle)

    assert aergo_validators == \
        aergo_validators_before + [aergo_validators_before[0]]

    # remove added validator
    aergo_nonce_before = int(
        hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
    )
    wallet.config_data('validators', value=new_validators[:-1])
    wallet.save_config()
    # wait for changes to be reflacted
    nonce = aergo_nonce_before
    while nonce <= aergo_nonce_before + 2:
        time.sleep(t_anchor_aergo)
        nonce = int(
            hera.query_sc_state(oracle, ["_sv__nonce"]).var_proofs[0].value
        )
    aergo_validators = query_validators(hera, oracle)

    assert aergo_validators == aergo_validators_before


def test_oracle_update(wallet):
    auto_update_oracle('sidechain2', 'mainnet', wallet)
    auto_update_oracle('mainnet', 'sidechain2', wallet)


def auto_update_oracle(from_chain, to_chain, wallet):
    hera = herapy.Aergo()
    hera.connect(wallet.config_data('networks', to_chain, 'ip'))
    oracle = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'oracle')
    bridge = wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'addr')
    default = wallet.config_data('wallet', 'default', 'addr')
    oracle_before = query_oracle(hera, bridge)
    assert oracle == oracle_before

    # set oracle to 'default' account in test_config
    new_oracle = default
    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'oracle',
        value=new_oracle
    )
    wallet.save_config()
    # wait for changes to be reflacted
    _, current_height = hera.get_blockchain_status()
    # waite for anchor containing our transfer
    stream = hera.receive_event_stream(
        bridge, "oracleUpdate", start_block_no=current_height)
    next(stream)
    stream.stop()
    oracle_after = query_oracle(hera, bridge)
    assert oracle_after == default

    wallet.config_data(
        'networks', to_chain, 'bridges', from_chain, 'oracle',
        value=oracle
    )
    wallet.save_config()
    # transfer bridge ownership back to oracle
    # set aergo signer
    encrypted_key = wallet.config_data('wallet', 'default', 'priv_key')
    hera.import_account(encrypted_key, '1234')
    hera.call_sc(bridge, "oracleUpdate", args=[oracle])
    time.sleep(2)
    oracle_after = query_oracle(hera, bridge)
    assert oracle == oracle_after
