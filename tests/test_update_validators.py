from bridge_operator.update_validators import ValidatorsManager

import copy
import json


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


def test_update_tempo():
    # TODO update one side at a time
    with open("./config.json", "r") as f:
        config_data = json.load(f)
    manager = ValidatorsManager(config_data)
    print(manager.get_t_final('mainnet', 'sidechain2'))
    sig1, sig2 = manager.sign_t_final(11, 'mainnet', 'sidechain2')
    manager.update_t_final(11,
                           [1, 2],
                           [sig1, sig1],
                           [sig2, sig2],
                           'mainnet', 'sidechain2')
    print(manager.get_t_final('mainnet', 'sidechain2'))
    sig1, sig2 = manager.sign_t_final(10, 'mainnet', 'sidechain2')
    manager.update_t_final(10,
                           [1, 2],
                           [sig1, sig1],
                           [sig2, sig2],
                           'mainnet', 'sidechain2')
    print(manager.get_t_final('mainnet', 'sidechain2'))
