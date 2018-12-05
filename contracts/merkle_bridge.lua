-- Merkle bridge contract

-- Stores latest finalised state root of connected blockchain at regular intervals.
-- Enables Users to verify state information of the connected chain 
-- using merkle proofs for the finalised state root.
state.var {
    Root = state.value(),
    Height = state.value(),
    Validators = state.map(),
    Val_Nb = state.value(),
    Locks = state.map(),
    Unlocks = state.map(),
    Burns = state.map(),
    Mints = state.map(),
    BridgeTokens = state.map(),
}

function constructor(addresses)
    Root:set("constructor")
    Height:set(0)
    Val_Nb:set(#addresses)
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
    if not validate_signatures(message, signers, signatures) then
        error("Failed signature validation")
    end
    Root:set(root)
    Height:set(height)
end

function validate_signatures(message, signers, signatures)
    -- 2/3 of Validators must sign for the message to be valid
    nb = Val_Nb:get()
    if nb*2 > #signers*3 then
        error("2/3 validators must sign")
    end
    for i,sig in ipairs(signers) do
        if not validate_sig(message, Validators[i], signatures[i]) then
            error("Invalid signature")
        end
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
    if not validate_signatures(message, signers, signatures) then
        error("Failed signature validation")
    end
    old_size = Val_Nb:get()
    if #addresses < old_size then
        diff = old_size - #addresses
        for i = 1, diff+1, 1 do
            -- delete validator slot
            Validators[old_size + i] = ""
        end
    end
    Val_Nb:set(#addresses)
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
    if amount <= 0 then
        error("amount must be positive")
    end
    if contract.getAmount() ~= 0 then
        if #token_address ~= 0 or amount ~= contract.getAmount() then
            error("wrong parameters for aergo bits lock up")
        end
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
        Locks[account_ref] = old + amount;
    end
end

-- mint a foreign token. token_origin is the token address where it is transfered from.
function mint(receiver_address, balance, token_origin, merkle_proof)
    account_ref = hash(receiver_address, token_origin)
    if balance <= 0 then
        error("minteable balance must be positive")
    end
    if not verify_mp(merkle_proof, "Locks", account_ref, balance, Root) then
        error("failed to verify deposit balance merkle proof")
    end
    minted_so_far = Mints[account_ref]
    if minted_so_far == nil then
        to_transfer = balance
    else
        to_transfer  = balance - minted_so_far
    end
    if to_transfer <= 0 then
        error("make a deposit before minting")
    end
    if BridgeTokens[token_origin] == nil then
        -- TODO Deploy new bridged token
        -- mint_address = new Token()
    else
        mint_address = BridgeTokens[token_origin]
    end
    Mints[account_ref] = balance
    if not contract.call(mint_address, "mint", receiver_address, to_transfer) then
        error("failed to mint token")
    end
end

-- origin_address is the address of the token on the parent chain.
function burn(receiver, amount, origin_address)
    if amount <= 0 then
        error("amount must be positive")
    end
    if contract.GetAmount() ~= 0 then
        error("burn function not payable, only tokens can be burned")
    end
    if BridgeTokens[origin_address] == nil then
        error("cannot burn token : must have been minted by bridge")
    end
    sender = system.getSender()
    burn_address = BridgeTokens[origin_address]
    if not contract.call(burn_address, "burn", sender, amount) then
        error("failed to burn token")
    end
    -- lock with the origin address information
    account_ref = hash(receiver, origin_address) 
    old = Burns[account_ref]
    if old == nil then
        Burns[account_ref] = amount;
    else
        Burns[account_ref] = old + amount;
    end
end

function unlock(receiver_address, balance, token_address, merkle_proof)
    account_ref = hash(receiver_address, token_address)
    if balance <= 0 then
        error("unlockeable balance must be positive")
    end
    if not verify_mp(merkle_proof, "Burns", account_ref, balance, Root) then
        error("failed to verify burnt balance merkle proof")
    end
    unlocked_so_far = Unlocks[account_ref]
    if unlocked_so_far == nil then
        to_transfer = balance
    else
        to_transfer = balance - unlocked_so_far
    end
    if to_transfer <= 0 then
        error("burn minted tokens before unlocking")
    end
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
