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

