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
    ContractID = state.value()
}

function constructor(total_supply) 
    Symbol:set("TOKEN")
    Name:set("Standard Token on Aergo")
    Decimals:set(18)
    TotalSupply:set(total_supply)
    Balances[system.getSender()] = total_supply
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
-- @param fee       fee given to the tx broadcaster
-- @param deadline  block number before which the tx can be executed
-- @param signature signature proving sender's consent
-- @return          success
---------------------------------------
function signed_transfer(from, to, value, nonce, fee, deadline, signature)
    -- TODO performance impact of data length in ecrecover
    assert(address.isValidAddress(to), "[transfer] invalid address format: " .. to)
    assert(address.isValidAddress(from), "invalid address format: " .. from)
    assert(to ~= from, "[transfer] same sender and receiver")
    assert(fee >= 0, "fee must be positive")
    assert(value >= 0, "value must be positive")
    assert(Balances[from] and (value + fee) <= Balances[from], "not enough balance")
    assert(deadline == 0 or system.getBlockheight() < deadline, "deadline has passed")
    data = crypto.sha256(to..tostring(value)..tostring(nonce)..tostring(fee)..tostring(deadline)..ContractID)
    assert(Nonces[from] + 1 == nonce, "nonce is invalid or already spent")
    assert(crypto.ecverify(data, signature, from), "signature of signed transfer is invalid")
    Balances[from] = safemath.sub(Balances[from], value + fee)
    Balances[to] = safemath.add(Balances[to], value)
    Balances[system.getSender()] = safemath.add(Balances[system.getSender()], fee)
    Nonces[from] = safemath.add(Nonces[from], 1)
    return true
end


-- register functions to abi
abi.register(transfer, signed_transfer)
