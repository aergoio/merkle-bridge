local address = {}
function address.isValidAddress(address)
  -- check existence of invalid alphabets
  if nil ~= string.match(address, '[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]') then
    return false
  end
  -- check lenght is in range
  if 52 ~= string.len(address) then
    return false
  end
  -- TODO add checksum verification
  return true
end


local safemath = {}
function safemath.add(a, b) 
    if a == nil then a = 0 end
    if b == nil then b = 0 end
    local c = a + b
    assert(c >= a)
    return c
end
function safemath.sub(a, b) 
    if a == nil then a = 0 end
    if b == nil then b = 0 end
    assert(b <= a, "first value must be bigger than second")
    local c = a - b
    return c
end

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
    -- The index of validators starts at 1.
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
    MintedTokens = state.map(),
    -- T_anchor is the anchoring periode of the bridge
    T_anchor = state.value(),
    -- T_final is the time after which the bridge operator consideres a block finalised
    T_final = state.value(),
}

function constructor(addresses, t_anchor, t_final)
    -- TODO make a setter for T_anchor and T_final with 2/3 sig validation
    T_anchor:set(t_anchor)
    T_final:set(t_final)
    Root:set("constructor")
    Height:set(0)
    Nb_Validators:set(#addresses)
    for i, addr in ipairs(addresses) do
        assert(address.isValidAddress(addr), "invalid address format: " .. addr)
        Validators[i] = addr
    end
end

-- signers is the index of signers in Validators
function set_root(root, height, signers, signatures)
    message = crypto.sha256(root..tostring(height))
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    Root:set(root)
    Height:set(height)
end

function validate_signatures(message, signers, signatures)
    -- 2/3 of Validators must sign for the message to be valid
    nb = Nb_Validators:get()
    assert(nb*2 <= #signers*3, "2/3 validators must sign")
    for i,signer in ipairs(signers) do
        assert(Validators[signer], "Signer index not registered")
        assert(crypto.ecverify(message, signatures[i], Validators[signer]), "Invalid signature")
    end
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
        assert(address.isValidAddress(addr), "invalid address format: " .. addr)
        Validators[i] = addr
    end
end

function hash(array)
    h = ""
    for i, data in ipairs(array) do
        h = h..data
    end
    return h
end

-- lock and burn must be distinct because tokens on both sides could have the same address. Also adds clarity because burning is only applicable to minted tokens.
-- nonce and signature are used when making a token lockup
function lock(receiver, amount, token_address, nonce, signature)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(MintedTokens[token_address] == nil, "this token was minted by the bridge so it should be burnt to transfer back to origin, not locked")
    assert(amount > 0, "amount must be positive")
    if contract.getAmount() ~= 0 then
        assert(#token_address == 0, "for safety and clarity don't provide a token address when locking aergo bits")
        assert(contract.getAmount() == amount, "for safety and clarity, amount must match the amount sent in the tx")
        token_address = "aergo"
   else
        sender = system.getSender()
        this_contract = system.getContractID()
        -- FIXME how can this be hacked with a reentrant call if the token_address is malicious ?
        if not contract.call(token_address, "signed_transfer", sender, this_contract, amount, nonce, signature) then
            error("failed to receive token to lock")
        end
    end
    account_ref = receiver .. token_address
    old = Locks[account_ref]
    if old == nil then
        locked_balance = amount
    else
        locked_balance = safemath.add(old, amount)
    end
    Locks[account_ref] = new_balance
    -- TODO add event
    return locked_balance
end

-- mint a foreign token. token_origin is the token address where it is transfered from.
function mint(receiver, balance, token_origin, merkle_proof)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(balance > 0, "minteable balance must be positive")
    account_ref = receiver .. token_origin
    if not _verify_mp(merkle_proof, "Locks", account_ref, balance, Root) then
        error("failed to verify deposit balance merkle proof")
    end
    minted_so_far = Mints[account_ref]
    if minted_so_far == nil then
        to_transfer = balance
    else
        to_transfer  = safemath.sub(balance, minted_so_far)
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
    if not contract.call(mint_address, "mint", receiver, to_transfer) then
        error("failed to mint token")
    end
    -- TODO add event
    return mint_address
end

-- origin_address is the address of the token on the parent chain.
function burn(receiver, amount, mint_address)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(amount > 0, "amount must be positive")
    assert(contract.GetAmount() == 0, "burn function not payable, only tokens can be burned")
    origin_address = MintedTokens[mint_address]
    assert(origin_address ~= nil, "cannot burn token : must have been minted by bridge")
    sender = system.getSender()
    if not contract.call(mint_address, "burn", sender, amount) then
        error("failed to burn token")
    end
    -- burn with the origin address information
    account_ref = receiver .. origin_address
    old = Burns[account_ref]
    if old == nil then
        burnt_balance = amount
    else
        burnt_balance = safemath.add(old,amount)
    end
    Burns[account_ref] = burnt_balance
    -- TODO add event
    return origin_address, burnt_balance
end

function unlock(receiver, balance, token_address, merkle_proof)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(balance > 0, "unlockeable balance must be positive")
    account_ref = receiver .. token_address
    if not _verify_mp(merkle_proof, "Burns", account_ref, balance, Root) then
        error("failed to verify burnt balance merkle proof")
    end
    unlocked_so_far = Unlocks[account_ref]
    if unlocked_so_far == nil then
        to_transfer = balance
    else
        to_transfer = safemath.sub(balance,unlocked_so_far)
    end
    assert(to_transfer > 0, "burn minted tokens before unlocking")
    Unlocks[account_ref] = balance
    if token_address == "aergo" then
        -- TODO does send return bool ?
        contract.send(receiver, to_transfer)
    else
        if not contract.call(token_address, "transfer", receiver, to_transfer) then
            error("failed to unlock token")
        end
    end
    -- TODO add event
end


function _verify_mp(mp, map_name, key, value, root)
    var_id = "_sv_" .. map_name .. key
    trie_key = hash(var_id)
    trie_value = hash(value)
    leaf_hash = hash(key, value, strchar(256-mp[3]))
    -- return root == _verify_proof(mp[1], trie_key, leafhash, mp[2], mp[3], 0, 0)
    return true
end

function _verify_proof(bitmap, key, leaf_hash, mp, length, key_index, mp_index)
    -- TODO
    -- requires support if bit_is_set and hash function by lua contract
end

abi.register(set_root, new_validators, lock, unlock, mint, burn)
