from bridge_operator.update_validators import ValidatorsManager

import copy
import json


# TODO deploy test bridge otherwise the update nonce is already spent

def test_update_validators():
    with open("./config.json", "r") as f:
        config_data = json.load(f)

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
                              'mainnet', 'sidechain2')
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
                              'mainnet', 'sidechain2')
    validators = manager.get_validators('mainnet', 'sidechain2')
    print("decreased number of validators  to : {}".format(len(validators[0])))
    print(validators)
    assert len(validators[0]) == 3


def test_update_t_anchor():
    with open("./config.json", "r") as f:
        config_data = json.load(f)

    manager = ValidatorsManager(config_data)
    t_anchor_before = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor before: ", t_anchor_before)

    sig = manager.sign_t_anchor(11, 'mainnet', 'sidechain2')
    manager.update_t_anchor(11,
                            [1, 2],
                            [sig, sig],
                            'mainnet', 'sidechain2')
    t_anchor_after = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor after: ", t_anchor_after)
    assert t_anchor_after == 11

    sig = manager.sign_t_anchor(t_anchor_before, 'mainnet', 'sidechain2')
    manager.update_t_anchor(t_anchor_before,
                            [1, 2],
                            [sig, sig],
                            'mainnet', 'sidechain2')

    t_anchor_after = manager.get_t_anchor('mainnet', 'sidechain2')
    print("t_anchor after: ", t_anchor_after)
    assert t_anchor_after == t_anchor_before


def test_update_t_final():
    with open("./config.json", "r") as f:
        config_data = json.load(f)

    manager = ValidatorsManager(config_data)
    t_final_before = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final before: ", t_final_before)

    sig = manager.sign_t_final(11, 'mainnet', 'sidechain2')
    manager.update_t_final(11,
                           [1, 2],
                           [sig, sig],
                           'mainnet', 'sidechain2')
    t_final_after = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final after: ", t_final_after)
    assert t_final_after == 11

    sig = manager.sign_t_final(t_final_before, 'mainnet', 'sidechain2')
    manager.update_t_final(t_final_before,
                           [1, 2],
                           [sig, sig],
                           'mainnet', 'sidechain2')

    t_final_after = manager.get_t_final('mainnet', 'sidechain2')
    print("t_final after: ", t_final_after)
    assert t_final_after == t_final_before
