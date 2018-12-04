-- Merkle bridge contract

-- Stores latest finalised state root of connected blockchain at regular intervals.
-- Enables Users to verify state information of the connected chain 
-- using merkle proofs for the finalised state root.
state.var {
    Root = state.value(),
    Height = state.value(),
    Validators = state.map(),
    Val_Nb = state.value(),
}

function constructor(addresses)
    Root:set("constructor")
    Height:set(0)
    Val_Nb:set(#addresses)
    for i, addr in ipairs(addresses) do
        Validators[i] = addr
    end
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

function hash(data)
    -- TODO use vm hash function instead
    return "hash_string"
end

abi.register(set_root, new_validators)
