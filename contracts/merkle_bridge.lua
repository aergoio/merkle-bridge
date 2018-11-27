-- Merkle bridge contract

-- Stores latest finalised state root of connected blockchain at regular intervals.
-- Enables Users to verify state information of the connected chain 
-- using merkle proofs for the finalised state root.
state.var {
    Root = state.value(),
    Validators = state.array(1),
}

function constructor(validators)
    for i, v in ipairs(validators) do
        Validators[i] = v
    end
end

function set_root(root, signatures)
    for i,sig in ipairs(signatures) do
        if not validate_signature(Validators[i], sig) then
            error("Invalid signature")
        end
    end
    Root:set(root)
end

function validate_signature(addr, sig)
    -- TODO ecrecover
    return true
end

abi.register(set_root)
