------------------------------------------------------------------------------
-- Merkle bridge contract
------------------------------------------------------------------------------

-- Internal type check function
-- @type internal
-- @param x variable to check
-- @param t (string) expected type
local function _typecheck(x, t)
  if (x and t == 'address') then
    assert(type(x) == 'string', "address must be string type")
    -- check address length
    assert(52 == #x, string.format("invalid address length: %s (%s)", x, #x))
    -- check character
    local invalidChar = string.match(x, '[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]')
    assert(nil == invalidChar, string.format("invalid address format: %s contains invalid char %s", x, invalidChar or 'nil'))
  elseif (x and t == 'ubig') then
    -- check unsigned bignum
    assert(bignum.isbignum(x), string.format("invalid type: %s != %s", type(x), t))
    assert(x >= bignum.number(0), string.format("%s must be positive number", bignum.tostring(x)))
  else
    -- check default lua types
    assert(type(x) == t, string.format("invalid type: %s != %s", type(x), t or 'nil'))
  end
end

-- Stores latest finalised state root of connected blockchain at regular intervals.
-- Enables Users to verify state information of the connected chain 
-- using merkle proofs for the finalised state root.
state.var {
    -- Trie root of the opposit side bridge contract. _mints and _unlocks require a merkle proof
    -- of state inclusion in this last Root.
    -- (hex string without 0x prefix)
    _anchorRoot = state.value(),
    -- Height of the last block anchored
    -- (hex string without 0x prefix)
    _anchorHeight = state.value(),
    -- _validators contains the addresses and 2/3 of them must sign a root update
    -- The index of validators starts at 1.
    -- (uint) -> (address) 
    _validators = state.map(),
    -- Number of validators registered in the Validators map
    -- (uint)
    _validatorsCount= state.value(),
    -- Registers locked balances per account reference: user provides merkle proof of locked balance
    -- (account ref string) -> (string uint)
    _locks = state.map(),
    -- Registers unlocked balances per account reference: prevents unlocking more than was burnt
    -- (account ref string) -> (string uint)
    _unlocks = state.map(),
    -- Registers burnt balances per account reference : user provides merkle proof of burnt balance
    -- (account ref string) -> (string uint)
    _burns = state.map(),
    -- Registers minted balances per account reference : prevents minting more than what was locked
    -- (account ref string) -> (string uint)
    _mints = state.map(),
    -- _bridgeTokens keeps track of tokens that were received through the bridge
    -- (address) -> (address)
    _bridgeTokens = state.map(),
    -- _mintedTokens is the same as _bridgeTokens but keys and values are swapped
    -- _mintedTokens is used for preventing a minted token from being locked instead of burnt.
    -- (address) -> (address)
    _mintedTokens = state.map(),
    -- _tAnchor is the anchoring periode of the bridge
    -- (uint)
    _tAnchor = state.value(),
    -- _tFinal is the time after which the bridge operator consideres a block finalised
    -- this value is only useful if the anchored chain doesn't have LIB.
    -- (uint)
    _tFinal = state.value(),
    -- _nonce is a replay protection for validator and root updates.
    -- (uint)
    _nonce = state.value(),
    -- _contractId is a replay protection between sidechains as the same addresses can be validators
    -- on multiple chains.
    -- (string)
    _contractId = state.value(),
}

--------------------- Utility Functions -------------------------
-- Check 2/3 validators signed message hash
-- @type    internal
-- @param   hash (0x hex string) 0x hex string 
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @return  (bool) 2/3 signarures are valid
local function _validateSignatures(hash, signers, signatures)
    -- 2/3 of _validators must sign for the hash to be valid
    nb = _validatorsCount:get()
    assert(nb*2 <= #signers*3, "2/3 validators must sign")
    for i,signer in ipairs(signers) do
        if i > 1 then
            assert(signer > signers[i-1], "All signers must be different")
        end
        assert(_validators[signer], "Signer index not registered")
        assert(crypto.ecverify(hash, signatures[i], _validators[signer]), "Invalid signature")
    end
    return true
end

-- Concatenate strings in array
-- @type    internal
-- @param   array ([]string)
-- @return  (string)
function _join(array)
    -- not using a separator is safe for signing if the length of items is checked with _typecheck for example
    str = ""
    for i, data in ipairs(array) do
        str = str..data
    end
    return str
end


-- check if the ith bit is set in hex string bytes
-- @type    internal
-- @param   bits (hex string) hex string without 0x
-- @param   i (uint) index of bit to check
-- @return  (bool) true if ith bit is 1
local function _bitIsSet(bits, i)
    require "bit"
    -- get the hex byte containing ith bit
    local byteIndex = math.floor(i/8)*2 + 1
    local byteHex = string.sub(bits, byteIndex, byteIndex + 1)
    local byte = tonumber(byteHex, 16)
    return bit.band(byte, bit.lshift(1,7-i%8)) ~= 0
end

-- compute the merkle proof verification
-- @type    internal
-- @param   ap ([]0x hex string) merkle proof nodes (audit path)
-- @param   keyIndex (uint) step counter in merkle proof iteration
-- @param   key (hex string) key for which the merkle proof is created
-- @param   leafHash (hex string) value stored in the smt
-- @return  (0x hex string) hash of the smt root with given merkle proof
local function _verifyProof(ap, keyIndex, key, leafHash)
    if keyIndex == #ap then
        return leafHash
    end
    if _bitIsSet(key, keyIndex) then
        local right = _verifyProof(ap, keyIndex+1, key, leafHash)
        return crypto.sha256("0x"..ap[#ap-keyIndex]..string.sub(right, 3, #right))
    end
    local left = _verifyProof(ap, keyIndex+1, key, leafHash)
    return crypto.sha256(left..ap[#ap-keyIndex])
end

-- We dont need to use compressed merkle proofs in lua because byte(0) is easilly 
-- passed in the merkle proof array.
-- (In solidity, only bytes32[] is supported, so byte(0) cannot be passed and it is
-- more efficient to use a compressed proof)
-- @type    internal
-- @param   ap ([]0x hex string) merkle proof nodes (audit path)
-- @param   mapName (string) name of mapping variable
-- @param   key (string) key stored in mapName
-- @param   value (string) value of key in mapName
-- @return  (bool) merkle proof of inclusion is valid
local function _verifyDepositProof(ap, mapName, key, value, root)
    local varId = "_sv_" .. mapName .. "-" .. key
    local trieKey = crypto.sha256(varId)
    local trieValue = crypto.sha256(value)
    local leafHash = crypto.sha256(trieKey..string.sub(trieValue, 3, #trieValue)..string.format('%02x', 256-#ap))
    return root == _verifyProof(ap, 0, string.sub(trieKey, 3, #trieKey), leafHash)
end

-- deploy new contract
-- @type    internal
-- @param   tokenOrigin (address) address of token locked used as pegged token name
local function _deployMintableToken(tokenOrigin)
    addr, success = contract.deploy(mintedToken, tokenOrigin)
    assert(success, "failed to create peg token contract")
    return addr
end

-- lock tokens in the bridge contract
-- @type    internal
-- @param   tokenAddress (address) token locked
-- @param   amount (ubig) amount of tokens to send
-- @param   receiver (address) receiver accross the bridge
-- @event   lock(receiver, amount, tokenAddress)
local function _lock(tokenAddress, amount, receiver)
    _typecheck(receiver, 'address')
    _typecheck(amount, 'ubig')
    assert(_mintedTokens[tokenAddress] == nil, "this token was minted by the bridge so it should be burnt to transfer back to origin, not locked")
    assert(amount > bignum.number(0), "amount must be positive")

    -- Add locked amount to total
    local accountRef = receiver .. tokenAddress
    local old = _locks[accountRef]
    local lockedBalance
    if old == nil then
        lockedBalance = amount
    else
        lockedBalance = bignum.number(old) + amount
    end
    _locks[accountRef] = bignum.tostring(lockedBalance)
    contract.event("lock", receiver, amount, tokenAddress)
end

-- Create a new bridge contract
-- @type    __init__
-- @param   validators ([]address) array of Aergo addresses
-- @param   tAnchor (uint) anchoring periode
-- @param   tFinal (uint) finality of anchored chain
-- @return  (string) id of contract to prevent anchor replay on other contracts
function constructor(validators, tAnchor, tFinal)
    _tAnchor:set(tAnchor)
    _tFinal:set(tFinal)
    _anchorRoot:set("constructor")
    _anchorHeight:set(0)
    _nonce:set(0)
    _validatorsCount:set(#validators)
    for i, addr in ipairs(validators) do
        _typecheck(addr, 'address')
        _validators[i] = addr
    end
    local id = crypto.sha256(system.getContractID()..system.getPrevBlockHash())
    -- contractID is the hash of system.getContractID (prevent replay between contracts on the same chain) and system.getPrevBlockHash (prevent replay between sidechains).
    -- take the first 16 bytes to save size of signed message
    id = string.sub(id, 3, 34)
    _contractId:set(id)
    return id
end

-- Register a new anchor
-- @type    call
-- @param   root (hex string) bytes of Aergo storage root
-- @param   height (uint) block height of root
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @event   newAnchor(proposer, height, root)
function newAnchor(root, height, signers, signatures)
    -- check Height so validator is not tricked by signing multiple anchors
    -- users have tAnchor to finalize their transfer
    -- (a malicious BP could commit a user's mint tx after newAnchor on purpose for user to lose tx fee.)
    assert(height > _anchorHeight:get() + _tAnchor:get(), "Next anchor height not reached")
    oldNonce = _nonce:get()
    -- NOTE if length of root is no checked, ',' is necessary
    message = crypto.sha256(root..','..tostring(height)..tostring(oldNonce).._contractId:get().."R")
    assert(_validateSignatures(message, signers, signatures), "Failed signature validation")
    _anchorRoot:set("0x"..root)
    _anchorHeight:set(height)
    _nonce:set(oldNonce + 1)
    contract.event("newAnchor", system.getSender(), height, root)
end

-- Register a new set of validators
-- @type    call
-- @param   validators ([]address) array of Aergo addresses
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @event   validatorsUpdate(proposer)
function validatorsUpdate(validators, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(_join(validators)..tostring(oldNonce).._contractId:get().."V")
    assert(_validateSignatures(message, signers, signatures), "Failed new validators signature validation")
    oldCount = _validatorsCount:get()
    if #validators < oldCount then
        diff = oldCount - #validators
        for i = 1, diff+1, 1 do
            -- delete validator slot
            _validators:delete(oldCount + i)
        end
    end
    _validatorsCount:set(#validators)
    for i, addr in ipairs(validators) do
        -- NOTE if length of addresses is not checked with _typecheck, then array items must be separated by a separator
        _typecheck(addr, 'address')
        _validators[i] = addr
    end
    _nonce:set(oldNonce + 1)
    contract.event("validatorsUpdate", system.getSender())
end

-- Register new anchoring periode
-- @type    call
-- @param   tAnchor (uint) new anchoring periode
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @event   tAnchorUpdate(proposer, tAnchor)
function tAnchorUpdate(tAnchor, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(tostring(tAnchor)..tostring(oldNonce).._contractId:get().."A")
    assert(_validateSignatures(message, signers, signatures), "Failed signature validation")
    _tAnchor:set(tAnchor)
    _nonce:set(oldNonce + 1)
    contract.event("tAnchorUpdate", system.getSender(), tAnchor)
end

-- Register new finality of anchored chain
-- @type    call
-- @param   tFinal (uint) new finality of anchored chain
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @event   tFinalUpdate(proposer, tFinal)
function tFinalUpdate(tFinal, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(tostring(tFinal)..tostring(oldNonce).._contractId:get().."F")
    assert(_validateSignatures(message, signers, signatures), "Failed signature validation")
    _tFinal:set(tFinal)
    _nonce:set(oldNonce + 1)
    contract.event("tFinalUpdate", system.getSender(), tFinal)
end

--------------------- User Transfer Functions -------------------------

-- The ARC1 smart contract calls this function on the recipient after a 'transfer'
-- @type    call
-- @param   operator    (address) the address which called token 'transfer' function
-- @param   from        (address) the sender's address
-- @param   value       (ubig) an amount of token to send
-- @param   receiver    (address) receiver accross the bridge
function tokensReceived(operator, from, value, receiver)
    return _lock(system.getSender(), value, receiver)
end

-- mint a token locked on a bidged chain
-- anybody can mint, the receiver is the account who's locked balance is recorded
-- @type    call
-- @param   receiver (address) designated receiver in lock
-- @param   balance (ubig) total balance of tokens locked
-- @param   tokenOrigin (address) token locked address on origin
-- @param   merkleProof ([]0x hex string) merkle proof of inclusion of locked balance
-- @return  (address, uint) pegged token Aergo address, minted amount
-- @event   mint(minter, receiver, amount, tokenOrigin)
function mint(receiver, balance, tokenOrigin, merkleProof)
    _typecheck(receiver, 'address')
    _typecheck(balance, 'ubig')
    _typecheck(tokenOrigin, 'address')
    assert(balance > bignum.number(0), "mintable balance must be positive")

    -- Verify merkle proof of locked balance
    local accountRef = receiver .. tokenOrigin
    local balanceStr = "\""..bignum.tostring(balance).."\""
    if not _verifyDepositProof(merkleProof, "_locks", accountRef, balanceStr, _anchorRoot:get()) then
        error("failed to verify deposit balance merkle proof")
    end
    -- Calculate amount to mint
    local amountToTransfer
    mintedSoFar = _mints[accountRef]
    if mintedSoFar == nil then
        amountToTransfer = balance
    else
        amountToTransfer  = balance - bignum.number(mintedSoFar)
    end
    assert(amountToTransfer > bignum.number(0), "make a deposit before minting")
    -- Deploy or get the minted token
    local mintAddress
    if _bridgeTokens[tokenOrigin] == nil then
        -- Deploy new mintable token controlled by bridge
        mintAddress = _deployMintableToken(tokenOrigin)
        _bridgeTokens[tokenOrigin] = mintAddress
        _mintedTokens[mintAddress] = tokenOrigin
    else
        mintAddress = _bridgeTokens[tokenOrigin]
    end
    -- Record total amount minted
    _mints[accountRef] = bignum.tostring(balance)
    -- Mint tokens
    contract.call(mintAddress, "mint", receiver, amountToTransfer)
    contract.event("mint", system.getSender(), receiver, amountToTransfer, tokenOrigin)
    return mintAddress, amountToTransfer
end

-- burn a pegged token
-- @type    call
-- @param   receiver (address) receiver accross the bridge
-- @param   amount (ubig) number of tokens to burn
-- @param   mintAddress (address) pegged token to burn
-- @return  (address) origin token to be unlocked
-- @event   brun(owner, receiver, amount, mintAddress)
function burn(receiver, amount, mintAddress)
    _typecheck(receiver, 'address')
    _typecheck(amount, 'ubig')
    assert(amount > bignum.number(0), "amount must be positive")
    local originAddress = _mintedTokens[mintAddress]
    assert(originAddress ~= nil, "cannot burn token : must have been minted by bridge")
    -- Add burnt amount to total
    local accountRef = receiver .. originAddress
    local old = _burns[accountRef]
    local burntBalance
    if old == nil then
        burntBalance = amount
    else
        burntBalance = bignum.number(old) + amount
    end
    _burns[accountRef] = bignum.tostring(burntBalance)
    -- Burn token
    contract.call(mintAddress, "burn", system.getSender(), amount)
    contract.event("burn", system.getSender(), receiver, amount, mintAddress)
    return originAddress
end

-- unlock tokens
-- anybody can unlock, the receiver is the account who's burnt balance is recorded
-- @type    call
-- @param   receiver (address) designated receiver in burn
-- @param   balance (ubig) total balance of tokens burnt
-- @param   tokenAddress (address) token to unlock
-- @param   merkleProof ([]0x hex string) merkle proof of inclusion of burnt balance
-- @return  (uint) unlocked amount
-- @event   unlock(unlocker, receiver, amount, tokenAddress)
function unlock(receiver, balance, tokenAddress, merkleProof)
    _typecheck(receiver, 'address')
    _typecheck(tokenAddress, 'address')
    _typecheck(balance, 'ubig')
    assert(balance > bignum.number(0), "unlockable balance must be positive")

    -- Verify merkle proof of burnt balance
    local accountRef = receiver .. tokenAddress
    local balanceStr = "\""..bignum.tostring(balance).."\""
    if not _verifyDepositProof(merkleProof, "_burns", accountRef, balanceStr, _anchorRoot:get()) then
        error("failed to verify burnt balance merkle proof")
    end

    -- Calculate amount to unlock
    local unlockedSoFar = _unlocks[accountRef]
    local amountToTransfer
    if unlockedSoFar == nil then
        amountToTransfer = balance
    else
        amountToTransfer = balance - bignum.number(unlockedSoFar)
    end
    assert(amountToTransfer > bignum.number(0), "burn minted tokens before unlocking")

    -- Record total amount unlocked so far
    _unlocks[accountRef] = bignum.tostring(balance)

    -- Unlock tokens
    contract.call(tokenAddress, "transfer", receiver, amountToTransfer)
    contract.event("unlock", system.getSender(), receiver, amountToTransfer, tokenAddress)
    return amountToTransfer
end


mintedToken = [[
------------------------------------------------------------------------------
-- Aergo Standard Token Interface (Proposal) - 20190731
------------------------------------------------------------------------------

-- A internal type check function
-- @type internal
-- @param x variable to check
-- @param t (string) expected type
local function _typecheck(x, t)
  if (x and t == 'address') then
    assert(type(x) == 'string', "address must be string type")
    -- check address length
    assert(52 == #x, string.format("invalid address length: %s (%s)", x, #x))
    -- check character
    local invalidChar = string.match(x, '[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]')
    assert(nil == invalidChar, string.format("invalid address format: %s contains invalid char %s", x, invalidChar or 'nil'))
  elseif (x and t == 'ubig') then
    -- check unsigned bignum
    assert(bignum.isbignum(x), string.format("invalid type: %s != %s", type(x), t))
    assert(x >= bignum.number(0), string.format("%s must be positive number", bignum.tostring(x)))
  else
    -- check default lua types
    assert(type(x) == t, string.format("invalid type: %s != %s", type(x), t or 'nil'))
  end
end

address0 = '1111111111111111111111111111111111111111111111111111'

-- The bridge token is a mintable and burnable token controlled by
-- the bridge contract. It represents tokens pegged on the other side of the 
-- bridge with a 1:1 ratio.
-- This contract is depoyed by the merkle bridge when a new type of token 
-- is transfered
state.var {
    _balances = state.map(), -- address -> unsigned_bignum
    _operators = state.map(), -- address/address -> bool

    _totalSupply = state.value(),
    _name = state.value(),
    _symbol = state.value(),
    _decimals = state.value(),

    _master = state.value(),
}

local function _callTokensReceived(from, to, value, ...)
  if to ~= address0 and system.isContract(to) then
    contract.call(to, "tokensReceived", system.getSender(), from, value, ...)
  end
end

local function _transfer(from, to, value, ...)
  _typecheck(from, 'address')
  _typecheck(to, 'address')
  _typecheck(value, 'ubig')

  assert(_balances[from] and _balances[from] >= value, "not enough balance")

  _balances[from] = _balances[from] - value
  _balances[to] = (_balances[to] or bignum.number(0)) + value

  _callTokensReceived(from, to, value, ...)

  contract.event("transfer", from, to, value)
end

local function _mint(to, value, ...)
  _typecheck(to, 'address')
  _typecheck(value, 'ubig')

  _totalSupply:set((_totalSupply:get() or bignum.number(0)) + value)
  _balances[to] = (_balances[to] or bignum.number(0)) + value

  _callTokensReceived(address0, to, value, ...)

  contract.event("transfer", address0, to, value)
end

local function _burn(from, value)
  _typecheck(from, 'address')
  _typecheck(value, 'ubig')

  assert(_balances[from] and _balances[from] >= value, "not enough balance")

  _totalSupply:set(_totalSupply:get() - value)
  _balances[from] = _balances[from] - value

  contract.event("transfer", from, address0, value)
end

-- call this at constructor
local function _init(name, symbol, decimals)
  _typecheck(name, 'string')
  _typecheck(symbol, 'string')
  _typecheck(decimals, 'number')
  assert(decimals > 0)

  _name:set(name)
  _symbol:set(symbol)
  _decimals:set(decimals)
end

------------  Main Functions ------------

-- Get a total token supply.
-- @type    query
-- @return  (ubig) total supply of this token
function totalSupply()
  return _totalSupply:get()
end

-- Get a token name
-- @type    query
-- @return  (string) name of this token
function name()
  return _name:get()
end

-- Get a token symbol
-- @type    query
-- @return  (string) symbol of this token
function symbol()
  return _symbol:get()
end

-- Get a token decimals
-- @type    query
-- @return  (number) decimals of this token
function decimals()
  return _decimals:get()
end

-- Get a balance of an owner.
-- @type    query
-- @param   owner  (address) a target address
-- @return  (ubig) balance of owner
function balanceOf(owner)
  return _balances[owner] or bignum.number(0)
end

-- Transfer sender's token to target 'to'
-- @type    call
-- @param   to      (address) a target address
-- @param   value   (ubig) an amount of token to send
-- @param   ...     addtional data, MUST be sent unaltered in call to 'tokensReceived' on 'to'
-- @event   transfer(from, to, value)
function transfer(to, value, ...)
  _transfer(system.getSender(), to, value, ...)
end

-- Get allowance from owner to spender
-- @type    query
-- @param   owner       (address) owner's address
-- @param   operator    (address) allowed address
-- @return  (bool) true/false
function isApprovedForAll(owner, operator)
  return (owner == operator) or (_operators[owner.."/".. operator] == true)
end

-- Allow operator to use all sender's token
-- @type    call
-- @param   operator  (address) a operator's address
-- @param   approved  (boolean) true/false
-- @event   approve(owner, operator, approved)
function setApprovalForAll(operator, approved)
  _typecheck(operator, 'address')
  _typecheck(approved, 'boolean')
  assert(system.getSender() ~= operator, "cannot set approve self as operator")

  _operators[system.getSender().."/".. operator] = approved

  contract.event("approve", system.getSender(), operator, approved)
end

-- Transfer 'from's token to target 'to'.
-- Tx sender have to be approved to spend from 'from'
-- @type    call
-- @param   from    (address) a sender's address
-- @param   to      (address) a receiver's address
-- @param   value   (ubig) an amount of token to send
-- @param   ...     addtional data, MUST be sent unaltered in call to 'tokensReceived' on 'to'
-- @event   transfer(from, to, value)
function transferFrom(from, to, value, ...)
  assert(isApprovedForAll(from, system.getSender()), "caller is not approved for holder")

  _transfer(from, to, value, ...)
end

-------------- Merkle Bridge functions -----------------
--------------------------------------------------------

-- Mint tokens to 'to'
-- @type        call
-- @param to    a target address
-- @param value string amount of token to mint
-- @return      success
function mint(to, value)
    assert(system.getSender() == _master:get(), "Only bridge contract can mint")
    _mint(to, value)
end

-- burn the tokens of 'from'
-- @type        call
-- @param from  a target address
-- @param value an amount of token to send
-- @return      success
function burn(from, value)
    assert(system.getSender() == _master:get(), "Only bridge contract can burn")
    _burn(from, value)
end

--------------- Custom constructor ---------------------
--------------------------------------------------------
function constructor(originAddress) 
    _init(originAddress, 'PEG', 18)
    _totalSupply:set(bignum.number(0))
    _master:set(system.getSender())
    return true
end
--------------------------------------------------------

abi.register(transfer, transferFrom, setApprovalForAll, mint, burn)
abi.register_view(name, symbol, decimals, totalSupply, balanceOf, isApprovedForAll)


]]

abi.register(newAnchor, validatorsUpdate, tAnchorUpdate, tFinalUpdate, tokensReceived, unlock, mint, burn)
