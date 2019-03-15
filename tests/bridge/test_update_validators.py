from bridge_operator.update_validators import ValidatorsManager

import aergo.herapy as herapy
import pytest

import copy
import json
import time


@pytest.fixture(scope="session", autouse=True)
def deploy_bridge():
    print("Deploying test bridge")
    mainnet = 'mainnet'
    sidechain = 'sidechain2'
    t_anchor = 10
    t_final = 10
    path = "./tests/bridge/config.json"
    with open(path, "r") as f:
        config_data = json.load(f)
    with open("./contracts/bridge_bytecode.txt", "r") as f:
        payload_str = f.read()[:-1]
    payload = herapy.utils.decode_address(payload_str)
    aergo1 = herapy.Aergo()
    aergo2 = herapy.Aergo()
    aergo1.connect(config_data[mainnet]['ip'])
    aergo2.connect(config_data[sidechain]['ip'])
    sender_priv_key = config_data["wallet"]['default2']['priv_key']
    aergo1.new_account(private_key=sender_priv_key)
    aergo2.new_account(private_key=sender_priv_key)
    validators = []
    for validator in config_data['validators']:
        validators.append(validator['addr'])
    tx1, result1 = aergo1.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor,
                                          t_final])
    tx2, result2 = aergo2.deploy_sc(amount=0,
                                    payload=payload,
                                    args=[validators,
                                          t_anchor,
                                          t_final])
    if result1.status != herapy.CommitStatus.TX_OK:
        print("Failed to commit deploy test bridge: {}, {}"
              .format(result1.status, result1.detail))
        assert 1 == 0
    if result2.status != herapy.CommitStatus.TX_OK:
        print("Failed to commit deploy test bridge: {}, {}"
              .format(result2.status, result2.detail))
        assert 1 == 0
    time.sleep(3)
    result1 = aergo1.get_tx_result(tx1.tx_hash)
    result2 = aergo2.get_tx_result(tx2.tx_hash)
    if result1.status != herapy.TxResultStatus.CREATED:
        print("Failed to execute deploy test bridge: {}, {}, {}"
              .format(result1.contract_address, result1.status,
                      result1.detail))
        assert 1 == 0
    if result2.status != herapy.TxResultStatus.CREATED:
        print("Failed to execute deploy test bridge: {}, {}, {}"
              .format(result2.contract_address, result2.status,
                      result2.detail))
        assert 1 == 0
    bridge_addr1 = result1.contract_address
    bridge_addr2 = result2.contract_address
    config_data[mainnet]['bridges'][sidechain] = {}
    config_data[sidechain]['bridges'][mainnet] = {}
    config_data[mainnet]['bridges'][sidechain]['addr'] = bridge_addr1
    config_data[sidechain]['bridges'][mainnet]['addr'] = bridge_addr2
    config_data[mainnet]['bridges'][sidechain]['t_anchor'] = t_anchor
    config_data[mainnet]['bridges'][sidechain]['t_final'] = t_final
    config_data[sidechain]['bridges'][mainnet]['t_anchor'] = t_anchor
    config_data[sidechain]['bridges'][mainnet]['t_final'] = t_final
    with open(path, "w") as f:
        json.dump(config_data, f, indent=4, sort_keys=True)


def test_update_validators():
    with open("./tests/bridge/config.json", "r") as f:
        config_data = json.load(f)

    # use the default wallet so it doesnt double spend a nonce if the proposer
    # is running
    sender_priv_key = config_data["wallet"]['default2']['priv_key']

    assert len(config_data['validators']) == 3, "fix config.json for tests"

    new_validators = ["AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474"]
    manager = ValidatorsManager(config_data)
    # 2/3 of the current validators must sign the new validators
    # atm gathering signatures is a manual voting process.
    sig1, sig2 = manager.sign_new_validators('mainnet', 'sidechain2',
                                             new_validators)
    # once the signatures sig1 and sig2 gathered, validators can be updated
    manager.update_validators(new_validators,
                              [1, 2],
                              [sig1, sig1],
                              [sig2, sig2],
                              'mainnet', 'sidechain2',
                              priv_key=sender_priv_key)
    validators = manager.get_validators('mainnet', 'sidechain2')
    print("increased number of validators to : {}".format(len(validators[0])))
    print(validators)
    assert len(validators[0]) == 4

    # simulate the new config.json with one extra validator
    new_config_data = copy.deepcopy(config_data)
    new_config_data['validators'].append(new_config_data['validators'][0])

    manager = ValidatorsManager(new_config_data)
    # test_config.json is the new config containing the updated 'validators'
    new_validators = ["AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474",
                      "AmPESicKLcPYXJC7ufgK6ti3fVS1r1SbqfxhVDEnTUc5cPXT1474"]
    manager = ValidatorsManager(new_config_data)
    sig1, sig2 = manager.sign_new_validators('mainnet', 'sidechain2',
                                             new_validators)
    manager.update_validators(new_validators,
                              [1, 2, 3],
                              [sig1, sig1, sig1],
                              [sig2, sig2, sig2],
                              'mainnet', 'sidechain2',
                              priv_key=sender_priv_key)
    validators = manager.get_validators('mainnet', 'sidechain2')
    print("decreased number of validators  to : {}".format(len(validators[0])))
    print(validators)
    assert len(validators[0]) == 3


def test_update_t_anchor():
    with open("./tests/bridge/config.json", "r") as f:
        config_data = json.load(f)
    # use the default wallet so it doesnt double spend a nonce if the proposer
    # is running
    sender_priv_key = config_data["wallet"]['default2']['priv_key']

    manager = ValidatorsManager(config_data)
    t_anchor_before = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor before: ", t_anchor_before)

    sig = manager.sign_t_anchor(11, 'mainnet', 'sidechain2')
    manager.update_t_anchor(11,
                            [1, 2],
                            [sig, sig],
                            'mainnet', 'sidechain2',
                            priv_key=sender_priv_key)
    t_anchor_after = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor after: ", t_anchor_after)
    assert t_anchor_after == 11

    sig = manager.sign_t_anchor(t_anchor_before, 'mainnet', 'sidechain2')
    manager.update_t_anchor(t_anchor_before,
                            [1, 2],
                            [sig, sig],
                            'mainnet', 'sidechain2',
                            priv_key=sender_priv_key)

    t_anchor_after = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor after: ", t_anchor_after)
    assert t_anchor_after == t_anchor_before


def test_update_t_final():
    with open("./tests/bridge/config.json", "r") as f:
        config_data = json.load(f)
    # use the default wallet so it doesnt double spend a nonce if the proposer
    # is running
    sender_priv_key = config_data["wallet"]['default2']['priv_key']

    manager = ValidatorsManager(config_data)
    t_final_before = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final before: ", t_final_before)

    sig = manager.sign_t_final(11, 'mainnet', 'sidechain2')
    manager.update_t_final(11,
                           [1, 2],
                           [sig, sig],
                           'mainnet', 'sidechain2',
                           priv_key=sender_priv_key)
    t_final_after = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final after: ", t_final_after)
    assert t_final_after == 11

    sig = manager.sign_t_final(t_final_before, 'mainnet', 'sidechain2')
    manager.update_t_final(t_final_before,
                           [1, 2],
                           [sig, sig],
                           'mainnet', 'sidechain2',
                           priv_key=sender_priv_key)

    t_final_after = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final after: ", t_final_after)
    assert t_final_after == t_final_before
