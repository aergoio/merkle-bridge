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
    TotalSupply:set(0)
    Owner:set(system.getSender())
end

---------------------------------------
-- Transfer sender's token to target 'to'
-- @type        call
-- @param to    a target address
-- @param value an amount of token to send
-- @return      success
---------------------------------------
function transfer(to, value)
    return _transfer(system.getSender(), to, value)
end

function _transfer(from, to, value) 
    assert(address.isValidAddress(to), "[transfer] invalid address format: " .. to)
    assert(to ~= from, "[transfer] same sender and receiver")
    assert(Balances[from] and value <= Balances[from], "[transfer] not enough balance")
    Balances[from] = safemath.sub(Balances[from], value)
    Nonces[from] = safemath.add(Nonces[from], 1)
    Balances[to] = safemath.add(Balances[to], value)
    -- TODO event notification
    return true
end

---------------------------------------
-- Transfer tokens according to signed data from the owner
-- @type  call
-- @param from      sender's address
-- @param to        receiver's address
-- @param value     an amount of token to send in aer
-- @param nonce     nonce of the sender to prevent replay
-- @param signature signature proving sender's consent
-- @return          success
---------------------------------------
function signed_transfer(from, to, value, nonce, signature)
    -- TODO performance impact of data length in ecrecover
    data = to .. value .. nonce .. ContractID
    assert(address.isValidAddress(from), "invalid address format: " .. from)
    assert(Nonces[from] + 1 == nonce, "nonce is invalid or already spent")
    assert(validate_sig(data, from, signature), "signature of signed transfer is invalid")
    return _transfer(from, to, value)
end

function validate_sig(message, expected_signer, signature)
    -- TODO ecrecover
    return true
end


---------------------------------------
-- Mint and Burn are specific to the token contract controlled by
-- the merkle bridge contract and representing transfered assets.
---------------------------------------

---------------------------------------
-- Mint tokens to 'to'
-- @type        call
-- @param to    a target address
-- @param value an amount of token to mint
-- @return      success
---------------------------------------
function mint(to, value)
    assert(address.isValidAddress(to), "invalid address format: " .. to)
    assert(system.getSender() == Owner, "Only bridge contract can mint")
    new_total = safemath.add(TotalSupply:get(), value)
    TotalSupply:set(new_total)
    Balances[to] = safemath.add(Balances[to], value);
    -- TODO event notification
    return true
end

---------------------------------------
-- Burn burns the tokens of 'from'
-- @type        call
-- @param from  a target address
-- @param value an amount of token to send
-- @return      success
---------------------------------------
function burn(from, value)
    assert(address.isValidAddress(from), "invalid address format: " ..from)
    assert(system.getSender() == Owner, "Only bridge contract can burn")
    assert(value <= Balances[from], "Not enough funds to burn")
    new_total = safemath.sub(TotalSupply:get(), value)
    TotalSupply:set(new_total)
    Balances[from] = safemath.sub(Balances[from], value)
    -- TODO event notification
    return true
end


-- register functions to abi
abi.register(transfer, signed_transfer, mint, burn)