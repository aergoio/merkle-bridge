-- Merkle bridge contract

-- Stores latest finalised state root of connected blockchain at regular intervals.
-- Enables Users to verify state information of the connected chain 
-- using merkle proofs for the finalised state root.
state.var {
    -- Trie root of the opposit side bridge contract. Mints and Unlocks require a merkle proof
    -- of state inclusion in this last Root.
    Root = state.value(),
    -- Height of the last block anchored
    Height = state.value(),
    -- Validators contains the addresses and 2/3 of them must sign a root update
    Validators = state.map(),
    -- Number of validators registered in the Validators map
    Nb_Validators= state.value(),
    -- Registers locked balances per account reference: user provides merkle proof of locked balance
    Locks = state.map(),
    -- Registers unlocked balances per account reference: prevents unlocking more than was burnt
    Unlocks = state.map(),
    -- Registers burnt balances per account reference : user provides merkle proof of burnt balance
    Burns = state.map(),
    -- Registers minted balances per account reference : prevents minting more than what was locked
    Mints = state.map(),
    -- BridgeTokens keeps track of tokens that were received through the bridge
    BridgeTokens = state.map(),
    -- MintedTokens is the same as BridgeTokens but keys and values are swapped
    -- MintedTokens is used for preventing a minted token from being locked instead of burnt.
    MintedTokens = state.map()
}

function constructor(addresses)
    Root:set("constructor")
    Height:set(0)
    Nb_Validators:set(#addresses)
    for i, addr in ipairs(addresses) do
        Validators[i] = addr
    end
end

function get_test()
    if BridgeTokens["a"] == nil then
        return 1
    end
    return BridgeTokens["a"]
end

-- signers is the index of signers in Validators
function set_root(root, height, signers, signatures)
    message = root..tostring(height)
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    Root:set(root)
    Height:set(height)
end

function validate_signatures(message, signers, signatures)
    -- 2/3 of Validators must sign for the message to be valid
    nb = Nb_Validators:get()
    assert(nb*2 <= #signers*3, "2/3 validators must sign")
    for i,sig in ipairs(signers) do
        assert(validate_sig(message, Validators[i], signatures[i]), "Invalid signature")
    end
    return true
end

function validate_sig(message, expected_signer, signature)
    -- TODO ecrecover
    return true
end

-- new_validators replaces the list of validators
-- signers is the index of signers in Validators
function new_validators(addresses, signers, signatures)
    message = hash(addresses)
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    old_size = Nb_Validators:get()
    if #addresses < old_size then
        diff = old_size - #addresses
        for i = 1, diff+1, 1 do
            -- TODO delete validator slot
            Validators[old_size + i] = ""
        end
    end
    Nb_Validators:set(#addresses)
    for i, addr in ipairs(addresses) do
        Validators[i] = addr
    end
end

function hash(...)
    -- TODO use vm hash function instead
    return "hash_string"
end

-- lock and burn must be distinct because tokens on both sides could have the same address. Also adds clarity because burning is only applicable to minted tokens.
function lock(receiver, amount, token_address)
    assert(MintedTokens[token_address] == nil, "this token was minted by the bridge so it should be burnt to transfer back to origin")
    assert(amount > 0, "amount must be positive")
    if contract.getAmount() ~= 0 then
        assert(#token_address == 0, "for safety and clarity don't provide a token address when locking aergo bits")
        assert(contract.getAmount() == amount, "for safety and clarity, amount must match the amount sent in the tx")
        token_address = "aergo"
   else
        sender = system.getSender()
        this_contract = system.getContractID()
        -- FIXME how can this be hacked with a reentrant call if the token_address is malicious ?
        if not contract.call(token_address, "transfer_from", sender, this_contract, amount) then
            error("failed to receive token to lock")
        end
    end
    account_ref = hash(receiver, token_address) 
    old = Locks[account_ref]
    if old == nil then
        Locks[account_ref] = amount;
    else
        -- TODO throw if old + amount > overflow : user should transfer through a different address
        Locks[account_ref] = old + amount;
    end
end

-- mint a foreign token. token_origin is the token address where it is transfered from.
function mint(receiver_address, balance, token_origin, merkle_proof)
    assert(balance > 0, "minteable balance must be positive")
    account_ref = hash(receiver_address, token_origin)
    if not verify_mp(merkle_proof, "Locks", account_ref, balance, Root) then
        error("failed to verify deposit balance merkle proof")
    end
    minted_so_far = Mints[account_ref]
    if minted_so_far == nil then
        to_transfer = balance
    else
        to_transfer  = balance - minted_so_far
    end
    assert(to_transfer > 0, "make a deposit before minting")
    if BridgeTokens[token_origin] == nil then
        -- TODO Deploy new bridged token
        -- mint_address = new Token()
        BridgeTokens[token_origin] = mint_address
        MintedTokens[mint_address] = token_origin
    else
        mint_address = BridgeTokens[token_origin]
    end
    Mints[account_ref] = balance
    if not contract.call(mint_address, "mint", receiver_address, to_transfer) then
        error("failed to mint token")
    end
    return mint_address
end

-- origin_address is the address of the token on the parent chain.
function burn(receiver, amount, mint_address)
    assert(amount > 0, "amount must be positive")
    assert(contract.GetAmount() == 0, "burn function not payable, only tokens can be burned")
    origin_address = MintedTokens[mint_address]
    assert(origin_address ~= nil, "cannot burn token : must have been minted by bridge")
    sender = system.getSender()
    if not contract.call(mint_address, "burn", sender, amount) then
        error("failed to burn token")
    end
    -- lock with the origin address information
    account_ref = hash(receiver, origin_address) 
    old = Burns[account_ref]
    if old == nil then
        Burns[account_ref] = amount;
    else
        -- TODO throw if old + amount > overflow : user should transfer through a different address
        Burns[account_ref] = old + amount;
    end
    return origin_address
end

function unlock(receiver_address, balance, token_address, merkle_proof)
    assert(balance > 0, "unlockeable balance must be positive")
    account_ref = hash(receiver_address, token_address)
    if not verify_mp(merkle_proof, "Burns", account_ref, balance, Root) then
        error("failed to verify burnt balance merkle proof")
    end
    unlocked_so_far = Unlocks[account_ref]
    if unlocked_so_far == nil then
        to_transfer = balance
    else
        to_transfer = balance - unlocked_so_far
    end
    assert(to_transfer > 0, "burn minted tokens before unlocking")
    Unlocks[account_ref] = balance
    if token_address == "aergo" then
        -- TODO does send return bool ?
        contract.send(receiver_address, to_transfer)
    else
        if not contract.call(token_address, "transfer", receiver_address, to_transfer) then
            error("failed to unlock token")
        end
    end
end


function verify_mp(mp, map_name, key, value, root)
    return true
end

abi.register(set_root, new_validators, lock, unlock, mint, burn, get_test)
