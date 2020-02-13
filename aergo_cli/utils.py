import PyInquirer as inquirer

aergo_style = inquirer.style_from_dict({
    inquirer.Token.Separator: '#FF36AD',
    inquirer.Token.QuestionMark: '#FF36AD bold',
    inquirer.Token.Selected: '',  # default
    inquirer.Token.Pointer: '#FF36AD bold',  # AWS orange
    inquirer.Token.Instruction: '',  # default
    inquirer.Token.Answer: '#FF36AD bold',  # AWS orange
    inquirer.Token.Question: 'bold',
})


def confirm_transfer():
    return promptYN(
        'Confirm you want to execute tranfer tx', 'Yes, execute transfer',
        'No, get me out of here!'
    )


def promptYN(q, y, n):
    """Prompt user to procede with a transfer of not."""
    questions = [
        {
            'type': 'list',
            'name': 'confirm',
            'message': q,
            'choices': [
                {
                    'name': y,
                    'value': True
                },
                {
                    'name': n,
                    'value': False
                }
            ]
        }
    ]
    answers = inquirer.prompt(questions, style=aergo_style)
    return answers['confirm']


def prompt_number(message, formator=int):
    """Prompt a number."""
    while 1:
        questions = [
            {
                'type': 'input',
                'name': 'num',
                'message': message
            }
        ]
        answers = inquirer.prompt(questions, style=aergo_style)
        try:
            num = formator(answers['num'])
            break
        except ValueError:
            print("Invalid number")
    return num


def prompt_amount():
    """Prompt a number of tokens to transfer."""
    return prompt_number("Amount of assets to transfer", format_amount)


def format_amount(num: str):
    """Format a float string to an integer with 18 decimals.

    Example:
        '2.3' -> 2300000000000000000

    """
    periode = num.find('.')
    if periode == -1:
        return int(num) * 10**18
    decimals = 0
    for i, digit in enumerate(num[periode + 1:]):
        decimals += int(digit) * 10**(17 - i)
    return int(num[:periode]) * 10**18 + decimals


def prompt_deposit_height():
    """Prompt the block number of deposit."""
    return prompt_number("Block height of deposit (0 to try finalization "
                         "anyway)")


def prompt_new_bridge(net1, net2):
    """Prompt user to input bridge contracts and tempo.

    For each contract on each bridged network, provide:
    - bridge contract address
    - anchoring periode
    - finality of the anchored chain

    """
    print('Bridge between {} and {}'.format(net1, net2))
    questions = [
        {
            'type': 'input',
            'name': 'bridge1',
            'message': 'Bridge contract address on {}'.format(net1)
        },
        {
            'type': 'input',
            'name': 't_anchor1',
            'message': 'Anchoring periode of {} on {}'.format(net2, net1)
        },
        {
            'type': 'input',
            'name': 't_final1',
            'message': 'Finality of {}'.format(net2)
        },
        {
            'type': 'input',
            'name': 'oracle1',
            'message': 'Oracle address on {}'.format(net1)
        },
        {
            'type': 'input',
            'name': 'bridge2',
            'message': 'Bridge contract address on {}'.format(net2)
        },
        {
            'type': 'input',
            'name': 't_anchor2',
            'message': 'Anchoring periode of {} on {}'.format(net1, net2)
        },
        {
            'type': 'input',
            'name': 't_final2',
            'message': 'Finality of {}'.format(net1)
        },
        {
            'type': 'input',
            'name': 'oracle2',
            'message': 'Oracle address on {}'.format(net2)
        },
    ]
    return inquirer.prompt(questions, style=aergo_style)


def prompt_new_network():
    """Prompt user to input a new network's information:
    - Name
    - IP/url

    """
    questions = [
        {
            'type': 'input',
            'name': 'name',
            'message': 'Network name'
        },
        {
            'type': 'input',
            'name': 'ip',
            'message': 'Network IP'
        }
    ]
    answers = inquirer.prompt(questions, style=aergo_style)
    return answers


def prompt_aergo_keystore():
    """Prompt user to register a new aergo keystore.

    Returns:
        - name of the key
        - address of the key
        - keystore path

    """
    questions = [
        {
            'type': 'input',
            'name': 'account_name',
            'message': 'Give your account a short descriptive name'
        },
        {
            'type': 'input',
            'name': 'keystore_path',
            'message': 'Path to keystore.json file'
        },
        {
            'type': 'input',
            'name': 'addr',
            'message': 'Aergo address matching private key'
        }
    ]
    answers = inquirer.prompt(questions, style=aergo_style)
    keystore_path = answers['keystore_path']
    account_name = answers['account_name']
    addr = answers['addr']
    return account_name, addr, keystore_path


def prompt_new_asset(networks):
    """Prompt user to input a new asset by providing the following:
    - asset name
    - origin network (where it was first issued)
    - address on origin network
    - other networks where the asset exists as a peg
    - address of pegs

    """
    questions = [
        {
            'type': 'input',
            'name': 'name',
            'message': "Asset name ('aergo' is "
                       "reserved for the real Aergo)"
        },
        {
            'type': 'list',
            'name': 'origin',
            'message': 'Origin network '
                       '(where the token was originally issued)',
            'choices': networks
        },
        {
            'type': 'input',
            'name': 'origin_addr',
            'message': 'Asset address'
        },
        {
            'type': 'list',
            'name': 'add_peg',
            'message': 'Add pegged asset on another network',
            'choices': [
                {
                    'name': 'Yes',
                    'value': True
                },
                {
                    'name': 'No',
                    'value': False
                }
            ]
        }
    ]
    answers = inquirer.prompt(questions, style=aergo_style)
    name = answers['name']
    origin = answers['origin']
    origin_addr = answers['origin_addr']
    networks.remove(origin)
    add_peg = answers['add_peg']
    pegs = []
    peg_addrs = []
    while add_peg:
        if len(networks) == 0:
            print('All pegged assets are registered in know networks')
            break
        questions = [
            {
                'type': 'list',
                'name': 'peg',
                'message': 'Pegged network',
                'choices': networks
            },
            {
                'type': 'input',
                'name': 'peg_addr',
                'message': 'Asset address'
            },
            {
                'type': 'list',
                'name': 'add_peg',
                'message': 'Add another pegged asset on another network',
                'choices': ['Yes', 'No']
            }
        ]
        answers = inquirer.prompt(questions, style=aergo_style)
        peg = answers['peg']
        peg_addr = answers['peg_addr']
        add_peg = answers['add_peg']
        networks.remove(peg)
        pegs.append(peg)
        peg_addrs.append(peg_addr)
    return name, origin, origin_addr, pegs, peg_addrs


def prompt_new_validators():
    """Prompt user to input validators

    Note:
        The list of validators must have the same order as defined in the
        bridge contracts

    Returns:
        List of ordered validators

    """

    print("WARNING : Validators must be registered in the correct order")
    validators = []
    add_val = True
    while add_val:
        questions = [
            {
                'type': 'input',
                'name': 'addr',
                'message': 'Aergo Address',
            },
            {
                'type': 'input',
                'name': 'ip',
                'message': 'Validator ip',
            },
            {
                'type': 'list',
                'name': 'add_val',
                'message': 'Add next validator ?',
                'choices': [
                    {
                        'name': 'Yes',
                        'value': True
                    },
                    {
                        'name': 'No',
                        'value': False
                    }
                ]
            }
        ]
        answers = inquirer.prompt(questions, style=aergo_style)
        validators.append({'addr': answers['addr'],
                           'ip': answers['ip']}
                          )
        add_val = answers['add_val']
    return validators


def print_balance_table_header():
    print(' ' + '_' * 120)
    print('|' + ' Name'.ljust(16) + '| Network'.ljust(24)
          + '| Token Address'.ljust(55) + '| Balance'.ljust(25) + '|')


def print_balance_table_lines(lines, token_name, col_widths):
    if len(lines) > 0:
        print('|' + '‾' * 16 + '|' + '‾' * 103 + '|')
        print('| ' + token_name.ljust(15) + '|'.ljust(104) + '|')
        for line in lines:
            print(
                '|' + '\t\t | '
                + "".join(col.ljust(col_widths[i])
                          for i, col in enumerate(line))
                + '|'
            )
