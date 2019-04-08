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
    -- Nonce is a replay protection for validator and root updates.
    Nonce = state.value(),
    -- LastAnchor
    LastAnchor = state.value(),
    -- ContractID is a replay protection between sidechains as the same addresses can be validators
    -- on multiple chains.
    ContractID = state.value(),

}

function constructor(addresses, t_anchor, t_final)
    T_anchor:set(t_anchor)
    T_final:set(t_final)
    Root:set("constructor")
    Height:set(0)
    Nonce:set(0)
    Nb_Validators:set(#addresses)
    for i, addr in ipairs(addresses) do
        assert(address.isValidAddress(addr), "invalid address format: " .. addr)
        Validators[i] = addr
    end
    local id = crypto.sha256(system.getContractID()..system.getPrevBlockHash())
    -- contractID is the hash of system.getContractID (prevent replay between contracts on the same chain) and system.getPrevBlockHash (prevent replay between sidechains).
    -- take the first 16 bytes to save size of signed message
    id = string.sub(id, 3, 32)
    ContractID:set(id)
    return id
end

-- signers is the index of signers in Validators
function set_root(root, height, signers, signatures)
    -- check Height so validator is not tricked by signing multiple anchors
    -- users have t_anchor to finalize their transfer
    -- TODO : a malicious BP could commit a user's mint tx after set_root on purpose for user to lose tx fee. -> deadline parameter in aergo tx.
    assert(height > Height:get() + T_anchor:get(), "Next anchor height not reached")
    old_nonce = Nonce:get()
    message = crypto.sha256(root..tostring(height)..tostring(old_nonce)..ContractID:get())
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    Root:set("0x"..root)
    Height:set(height)
    Nonce:set(old_nonce + 1)
end

function validate_signatures(message, signers, signatures)
    -- 2/3 of Validators must sign for the message to be valid
    nb = Nb_Validators:get()
    assert(nb*2 <= #signers*3, "2/3 validators must sign")
    for i,signer in ipairs(signers) do
        if i > 1 then
            assert(signer > signers[i-1], "All signers must be different")
        end
        assert(Validators[signer], "Signer index not registered")
        assert(crypto.ecverify(message, signatures[i], Validators[signer]), "Invalid signature")
    end
    return true
end

-- new_validators replaces the list of validators
-- signers is the index of signers in Validators
function update_validators(addresses, signers, signatures)
    old_nonce = Nonce:get()
    message = crypto.sha256(join(addresses)..tostring(old_nonce)..ContractID:get())
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    old_size = Nb_Validators:get()
    if #addresses < old_size then
        diff = old_size - #addresses
        for i = 1, diff+1, 1 do
            -- delete validator slot
            Validators:delete(old_size + i)
        end
    end
    Nb_Validators:set(#addresses)
    for i, addr in ipairs(addresses) do
        assert(address.isValidAddress(addr), "invalid address format: " .. addr)
        Validators[i] = addr
    end
    Nonce:set(old_nonce + 1)
end

function update_t_anchor(t_anchor, signers, signatures)
    old_nonce = Nonce:get()
    message = crypto.sha256(tostring(t_anchor)..tostring(old_nonce)..ContractID:get())
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    T_anchor:set(t_anchor)
    Nonce:set(old_nonce + 1)
end

function update_t_final(t_final, signers, signatures)
    old_nonce = Nonce:get()
    message = crypto.sha256(tostring(t_final)..tostring(old_nonce)..ContractID:get())
    assert(validate_signatures(message, signers, signatures), "Failed signature validation")
    T_final:set(t_final)
    Nonce:set(old_nonce + 1)
end

function join(array)
    str = ""
    for i, data in ipairs(array) do
        str = str..data
    end
    return str
end

-- lock and burn must be distinct because tokens on both sides could have the same address. Also adds clarity because burning is only applicable to minted tokens.
-- nonce and signature are used when making a token lockup
-- the owner of tokens can use a broadcaster and pay fees in tokens instead of aer
function lock(receiver, amount, token_address, nonce, signature, fee, deadline)
    local bamount = bignum.number(amount)
    local b0 = bignum.number(0)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(MintedTokens[token_address] == nil, "this token was minted by the bridge so it should be burnt to transfer back to origin, not locked")
    assert(bamount > b0, "amount must be positive")

    -- Lock assets/aer in the bridge
    if system.getAmount() ~= "0" then
        assert(token_address == "aergo", "for safety and clarity don't provide a token address when locking aergo bits")
        assert(system.getAmount() == bignum.tostring(bamount), "for safety and clarity, amount must match the amount sent in the tx")
   else
        this_contract = system.getContractID()
        -- FIXME how can this be hacked with a reentrant call if the token_address is malicious ?
        if fee == nil then
            sender = system.getSender()
            if not contract.call(token_address, "signed_transfer", sender, this_contract, bignum.tostring(bamount), nonce, signature, "0", 0) then
                error("failed to receive token to lock")
            end
        else
            -- the owner of tokens doesn't pay aer fees, lock is called by a broadcaster
            if not contract.call(token_address, "signed_transfer", receiver, this_contract, bignum.tostring(bamount), nonce, signature, fee, deadline) then
                error("failed to receive token to lock")
            end
            -- hack : take the token signature from lock tx and create a new tx with a different receiver, include that tx before the first one. 
            -- fix : the token sender should sign receiver (he does when sender=system.getSender() but doesnt if the tx is broadcasted, so sender should equal receiver in that case).
        end
    end

    -- Add locked amount to total
    local account_ref = receiver .. token_address
    local old = Locks[account_ref]
    local locked_balance
    if old == nil then
        locked_balance = bamount
    else
        locked_balance = bignum.number(old) + bamount
    end
    Locks[account_ref] = bignum.tostring(locked_balance)
    -- TODO add event
    return token_address, bamount
end

-- mint a foreign token. token_origin is the token address where it is transfered from.
-- anybody can mint, the receiver is the account who's locked balance is recorded
-- mint tx fees cannot be payed in tokens (let's the sidechain mint without user having to sign
-- a delegated mint : better UX if minting handled by sidechain.)
function mint(receiver, balance, token_origin, merkle_proof)
    local bbalance = bignum.number(balance)
    local b0 = bignum.number(0)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(bbalance > b0, "minteable balance must be positive")

    -- Verify merkle proof of locked balance
    local account_ref = receiver .. token_origin
    local balance_str = "\""..bignum.tostring(bbalance).."\""
    if not _verify_mp(merkle_proof, "Locks", account_ref, balance_str, Root:get()) then
        error("failed to verify deposit balance merkle proof")
    end

    -- Calculate amount to mint
    local to_transfer
    minted_so_far = Mints[account_ref]
    if minted_so_far == nil then
        to_transfer = bbalance
    else
        to_transfer  = bbalance - bignum.number(minted_so_far)
    end
    assert(to_transfer > bignum.number(0), "make a deposit before minting")

    -- Deploy or get the minted token
    local mint_address
    if BridgeTokens[token_origin] == nil then
        -- Deploy new minteable token controlled by bridge
        mint_address, success = _deploy_minteable_token()
        if not success then error("failed to create token contract") end
        BridgeTokens[token_origin] = mint_address
        MintedTokens[mint_address] = token_origin
    else
        mint_address = BridgeTokens[token_origin]
    end

    -- Record total amount minted
    Mints[account_ref] = bignum.tostring(bbalance)

    -- Mint tokens
    if not contract.call(mint_address, "mint", receiver, bignum.tostring(to_transfer)) then
        error("failed to mint token")
    end
    -- TODO add event
    return mint_address, to_transfer
end

-- burn a sidechain token
-- mint_address is the token address on the sidechain
-- the owner of tokens can use a broadcaster and pay fees in tokens instead of aer
function burn(receiver, amount, mint_address, nonce, signature, fee, deadline)
    local bamount = bignum.number(amount)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(bamount > bignum.number(0), "amount must be positive")
    assert(system.getAmount() == "0", "burn function not payable, only tokens can be burned")

    -- Burn token
    local origin_address = MintedTokens[mint_address]
    assert(origin_address ~= nil, "cannot burn token : must have been minted by bridge")
    if fee == nil then
        sender = system.getSender()
        if not contract.call(mint_address, "burn", sender, bignum.tostring(bamount)) then
            error("failed to burn token")
        end
    else
        -- the owner of tokens doesn't pay aer fees, burn is called by a broadcaster
        if not contract.call(mint_address, "signed_burn", receiver, bignum.tostring(bamount), nonce, signature, fee, deadline) then
            error("failed to burn token")
        end
        -- hack : take the token signature from burn tx and create a new tx with a different receiver, include that tx before the first one.
        -- fix : the token sender should sign receiver (he does when sender=system.getSender() but doesnt if the tx is broadcasted, so sender should equal receiver in that case).
    end

    -- Add burnt amount to total
    local account_ref = receiver .. origin_address
    local old = Burns[account_ref]
    local burnt_balance
    if old == nil then
        burnt_balance = bamount
    else
        burnt_balance = bignum.number(old) + bamount
    end
    Burns[account_ref] = bignum.tostring(burnt_balance)
    -- TODO add event
    return origin_address, bamount
end

-- unlock tokens returning from sidechain
-- anybody can unlock, the receiver is the account who's burnt balance is recorded
-- unlock tx fees cannot be payed in tokens (let's the sidechain unlock without user having to sign
-- a delegated unlock : better UX if unlocking handled by sidechain, fees can still be payed at burn time)
function unlock(receiver, balance, token_address, merkle_proof)
    local bbalance = bignum.number(balance)
    assert(address.isValidAddress(receiver), "invalid address format: " .. receiver)
    assert(bbalance > bignum.number(0), "unlockeable balance must be positive")

    -- Verify merkle proof of burnt balance
    local account_ref = receiver .. token_address
    local balance_str = "\""..bignum.tostring(bbalance).."\""
    if not _verify_mp(merkle_proof, "Burns", account_ref, balance_str, Root:get()) then
        error("failed to verify burnt balance merkle proof")
    end

    -- Calculate amount to unlock
    local unlocked_so_far = Unlocks[account_ref]
    local to_transfer
    if unlocked_so_far == nil then
        to_transfer = bbalance
    else
        to_transfer = bbalance - bignum.number(unlocked_so_far)
    end
    assert(to_transfer > bignum.number(0), "burn minted tokens before unlocking")

    -- Record total amount unlocked so far
    Unlocks[account_ref] = bignum.tostring(bbalance)

    -- Unlock tokens/aer
    if token_address == "aergo" then
        contract.send(receiver, to_transfer)
    else
        if not contract.call(token_address, "transfer", receiver, bignum.tostring(to_transfer)) then
            error("failed to unlock token")
        end
    end
    -- TODO add event
    return token_address, to_transfer
end


-- We dont need to use compressed merkle proofs in lua because byte(0) is easilly 
-- passed in the merkle proof array.
-- (In solidity, only bytes32[] is supported, so byte(0) cannot be passed and it is
-- more efficient to use a compressed proof)
function _verify_mp(ap, map_name, key, value, root)
    local var_id = "_sv_" .. map_name .. "-" .. key
    local trie_key = crypto.sha256(var_id)
    local trie_value = crypto.sha256(value)
    local leaf_hash = crypto.sha256(trie_key..string.sub(trie_value, 3, #trie_value)..string.format('%02x', 256-#ap))
    return root == _verify_proof(ap, 0, string.sub(trie_key, 3, #trie_key), leaf_hash)
end

function _verify_proof(ap, key_index, key, leaf_hash)
    if key_index == #ap then
        return leaf_hash
    end
    if _bit_is_set(key, key_index) then
        local right = _verify_proof(ap, key_index+1, key, leaf_hash)
        return crypto.sha256("0x"..ap[#ap-key_index]..string.sub(right, 3, #right))
    end
    local left = _verify_proof(ap, key_index+1, key, leaf_hash)
    return crypto.sha256(left..ap[#ap-key_index])
end

function _bit_is_set(bits, i)
    require "bit"
    -- get the hex byte containing ith bit
    local byte_index = math.floor(i/8)*2 + 1
    local byte_hex = string.sub(bits, byte_index, byte_index + 1)
    local byte = tonumber(byte_hex, 16)
    return bit.band(byte, bit.lshift(1,7-i%8)) ~= 0
end

function _deploy_minteable_token()
    src = [[
local type_check = {}
function type_check.isValidAddress(address)
    -- check existence of invalid alphabets
    if nil ~= string.match(address, '[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]') then
        return false
    end
    -- check lenght is in range
    if 52 ~= string.len(address) then
        return false
    end
    -- TODO add checksum verification?
    return true
end
function type_check.isValidNumber(value)
    if nil ~= string.match(value, '[^0123456789]') then
        return false
    end
    return true
end


-- The a bridge token is a mintable and burnable token controlled by
-- the bridge contract. It represents all tokens locked on the other side of the 
-- bridge with a 1:1 ratio.
-- This contract is depoyed by the merkle bridge when a new type of token 
-- is transfered
state.var {
    Symbol = state.value(),
    Name = state.value(),
    Decimals = state.value(),
    TotalSupply = state.value(),
    Balances = state.map(),
    Nonces = state.map(),
    -- Contract ID is a unique id that cannot be shared by another contract, even one on a sidechain
    -- This is neeeded for replay protection of signed transfer, because users might have the same private key
    -- on different sidechains
    ContractID = state.value(),
    Owner = state.value(),
}

function constructor() 
    Symbol:set("TOKEN")
    Name:set("Standard Token on Aergo")
    Decimals:set(18)
    TotalSupply:set(bignum.number(0))
    Owner:set(system.getSender())
    -- contractID is the hash of system.getContractID (prevent replay between contracts on the same chain) and system.getPrevBlockHash (prevent replay between sidechains).
    -- take the first 16 bytes to save size of signed message
    local id = crypto.sha256(system.getContractID()..system.getPrevBlockHash())
    id = string.sub(id, 3, 32)
    ContractID:set(id)
    return true
end

---------------------------------------
-- Transfer sender's token to target 'to'
-- @type        call
-- @param to    a target address
-- @param value string amount of tokens to send
-- @return      success
---------------------------------------
function transfer(to, value) 
    assert(type_check.isValidNumber(value), "invalid value format (must be string)")
    assert(type_check.isValidAddress(to), "invalid address format: " .. to)
    local from = system.getSender()
    local bvalue = bignum.number(value)
    local b0 = bignum.number(0)
    assert(bvalue > b0, "invalid value")
    assert(to ~= from, "same sender and receiver")
    assert(Balances[from] and bvalue <= Balances[from], "not enough balance")
    Balances[from] = Balances[from] - bvalue
    Nonces[from] = (Nonces[from] or 0) + 1
    Balances[to] = (Balances[to] or b0) + bvalue
    -- TODO event notification
    return true
end

---------------------------------------
-- Transfer tokens according to signed data from the owner
-- @type  call
-- @param from      sender's address
-- @param to        receiver's address
-- @param value     string amount of token to send in aer
-- @param nonce     nonce of the sender to prevent replay
-- @param fee       string fee given to the tx broadcaster
-- @param deadline  block number before which the tx can be executed
-- @param signature signature proving sender's consent
-- @return          success
---------------------------------------
function signed_transfer(from, to, value, nonce, signature, fee, deadline)
    assert(type_check.isValidNumber(value), "invalid value format (must be string)")
    assert(type_check.isValidNumber(fee), "invalid fee format (must be string)")
    local bfee = bignum.number(fee)
    local bvalue = bignum.number(value)
    local b0 = bignum.number(0)
    -- check addresses
    assert(type_check.isValidAddress(to), "invalid address format: " .. to)
    assert(type_check.isValidAddress(from), "invalid address format: " .. from)
    assert(to ~= from, "same sender and receiver")
    -- check amounts, fee
    assert(bfee >= b0, "fee must be positive")
    assert(bvalue >= b0, "value must be positive")
    assert(Balances[from] and (bvalue+bfee) <= Balances[from], "not enough balance")
    -- check deadline
    assert(deadline == 0 or system.getBlockheight() < deadline, "deadline has passed")
    -- check nonce
    if Nonces[from] == nil then Nonces[from] = 0 end
    assert(Nonces[from] == nonce, "nonce is invalid or already spent")
    -- construct signed transfer and verifiy signature
    data = crypto.sha256(to..bignum.tostring(bvalue)..tostring(nonce)..bignum.tostring(bfee)..tostring(deadline)..ContractID:get())
    assert(crypto.ecverify(data, signature, from), "signature of signed transfer is invalid")
    -- execute transfer
    Balances[from] = Balances[from] - bvalue - bfee
    Balances[to] = (Balances[to] or b0) + bvalue
    Balances[system.getOrigin()] = (Balances[system.getOrigin()] or b0) + bfee
    Nonces[from] = Nonces[from] + 1
    -- TODO event notification
    return true
end


---------------------------------------
-- mint, burn and signed_burn are specific to the token contract controlled by
-- the merkle bridge contract and representing transfered assets.
---------------------------------------

---------------------------------------
-- Mint tokens to 'to'
-- @type        call
-- @param to    a target address
-- @param value string amount of token to mint
-- @return      success
---------------------------------------
function mint(to, value)
    assert(system.getSender() == Owner:get(), "Only bridge contract can mint")
    assert(type_check.isValidNumber(value), "invalid value format (must be string)")
    local bvalue = bignum.number(value)
    local b0 = bignum.number(0)
    assert(type_check.isValidAddress(to), "invalid address format: " .. to)
    local new_total = TotalSupply:get() + bvalue
    TotalSupply:set(new_total)
    Balances[to] = (Balances[to] or b0) + bvalue;
    -- TODO event notification
    return true
end

---------------------------------------
-- burn the tokens of 'from'
-- @type        call
-- @param from  a target address
-- @param value an amount of token to send
-- @return      success
---------------------------------------
function burn(from, value)
    assert(system.getSender() == Owner:get(), "Only bridge contract can burn")
    assert(type_check.isValidNumber(value), "invalid value format (must be string)")
    local bvalue = bignum.number(value)
    local b0 = bignum.number(0)
    assert(type_check.isValidAddress(from), "invalid address format: " ..from)
    assert(Balances[from] and bvalue <= Balances[from], "Not enough funds to burn")
    new_total = TotalSupply:get() - bvalue
    TotalSupply:set(new_total)
    Balances[from] = Balances[from] - bvalue
    -- TODO event notification
    return true
end

---------------------------------------
-- signed_burn the tokens of 'from' according to signed data from the owner
-- @type            call
-- @param from      a target address
-- @param value     an amount of token to send
-- @param nonce     nonce of the sender to prevent replay
-- @param fee       string fee given to the tx broadcaster
-- @param deadline  block number before which the tx can be executed
-- @param signature signature proving sender's consent
-- @return          success
---------------------------------------
function signed_burn(from, value, nonce, signature, fee, deadline)
    assert(system.getSender() == Owner:get(), "Only bridge contract can burn")
    assert(type_check.isValidNumber(value), "invalid value format (must be string)")
    assert(type_check.isValidNumber(fee), "invalid fee format (must be string)")
    local bfee = bignum.number(fee)
    local bvalue = bignum.number(value)
    local b0 = bignum.number(0)
    -- check addresses
    assert(type_check.isValidAddress(from), "invalid address format: " .. from)
    -- check amounts, fee
    assert(bfee >= b0, "fee must be positive")
    assert(bvalue >= b0, "value must be positive")
    assert(Balances[from] and (bvalue+bfee) <= Balances[from], "not enough balance")
    -- check deadline
    assert(deadline == 0 or system.getBlockheight() < deadline, "deadline has passed")
    -- check nonce
    if Nonces[from] == nil then Nonces[from] = 0 end
    assert(Nonces[from] == nonce, "nonce is invalid or already spent")
    -- construct signed transfer and verifiy signature
    data = crypto.sha256(system.getSender()..bignum.tostring(bvalue)..tostring(nonce)..bignum.tostring(bfee)..tostring(deadline)..ContractID:get())
    assert(crypto.ecverify(data, signature, from), "signature of signed transfer is invalid")
    -- execute burn
    new_total = TotalSupply:get() - bvalue
    TotalSupply:set(new_total)
    Balances[from] = Balances[from] - bvalue - bfee
    Balances[system.getOrigin()] = (Balances[system.getOrigin()] or b0) + bfee
    Nonces[from] = Nonces[from] + 1
    -- TODO event notification
    return true
end


-- register functions to abi
abi.register(transfer, signed_transfer, mint, burn, signed_burn)
        ]]
    addr, success = contract.deploy(src)
    return addr, success
end

abi.register(set_root, update_validators, update_t_anchor, update_t_final, lock, unlock, mint, burn)
abi.payable(lock)
