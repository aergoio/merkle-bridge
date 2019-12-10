------------------------------------------------------------------------------
-- Oracle contract
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
  else
    -- check default lua types
    assert(type(x) == t, string.format("invalid type: %s != %s", type(x), t or 'nil'))
  end
end

state.var {
    -- Global State root included in block headers
    -- (0x hex string)
    _anchorRoot = state.value(),
    -- Height of the last block anchored
    -- (uint)
    _anchorHeight = state.value(),

    -- _tAnchor is the anchoring periode: sets a minimal delay between anchors to prevent spamming
    -- and give time to applications to build merkle proof for their data.
    -- (uint)
    _tAnchor = state.value(),
    -- _tFinal is the time after which the validators considere a block finalised
    -- this value is only useful if the anchored chain doesn't have LIB
    -- Since Aergo has LIB it is a simple indicator for wallets.
    -- (uint)
    _tFinal = state.value(),
    -- _validators contains the addresses and 2/3 of them must sign a root update
    -- The index of validators starts at 1.
    -- (uint) -> (address) 
    _validators = state.map(),
    -- Number of validators registered in the Validators map
    -- (uint)
    _validatorsCount = state.value(),
    -- _nonce is a replay protection for validator and root updates.
    -- (uint)
    _nonce = state.value(),
    -- _contractId is a replay protection between sidechains as the same addresses can be validators
    -- on multiple chains.
    -- (string)
    _contractId = state.value(),
    -- address of the bridge contract being controlled by oracle
    _bridge = state.value(),
    -- address of the bridge contract being controlled by oracle
    -- General Aergo state trie key of the bridge contract on connected blockchain
    -- (0x hex string)
    _destinationBridgeKey = state.value(),
}

--------------------- Utility Functions -------------------------
-- Check 2/3 validators signed message hash
-- @type    query
-- @param   hash (0x hex string)
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @return  (bool) 2/3 signarures are valid
function validateSignatures(hash, signers, signatures)
    -- 2/3 of Validators must sign for the hash to be valid
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
-- @type    query
-- @param   array ([]string)
-- @return  (string)
function join(array)
    -- not using a separator is safe for signing if the length of items is checked with isValidAddress for example
    str = ""
    for i, data in ipairs(array) do
        str = str..data
    end
    return str
end

-- Parse a proto serialized contract account state to extract the storage root
-- @type    query
-- @param   proto (0x hex string) serialized proto account
function parseRootFromProto(proto)
   --[[
        message State {
            uint64 nonce = 1;
            bytes balance = 2;
            bytes codeHash = 3;
            bytes storageRoot = 4;
            uint64 sqlRecoveryPoint = 5;
        }
        https://developers.google.com/protocol-buffers/docs/encoding

        +--------------+-----------+----------+--------------+
        | field number | wire type | tag(hex) |   tag(bin)   |
        |       1      |     0     |   0x08   |   0000 1000  |
        |       2      |     2     |   0x12   |   0001 0010  |
        |       3      |     2     |   0x1a   |   0001 1010  |
        |       4      |     2     |   0x22   |   0010 0010  |
        |       5      |     0     |   0x2a   |   0010 1010  |
        +--------------+-----------+----------+--------------+

        Contracts can have 0 balance and 0 nonce, so their tags 0x08 and 0x12 are not always present
        in the serialized state.
    ]]
    -- keep track of byte index while steping through the proto bytes.
    -- start at index 3 to skip 0x prefix in proto
    local index = 3

    -- parse uint64 nonce = 1
    if string.sub(proto, index, index + 1) == "08" then
        index = index + 2
        for i = index, #proto, 2 do
            -- 0x80 = 128 => check if the first bit is 0 or 1.
            -- The first bit of the last byte of the varint nb is 0
            if tonumber(string.sub(proto, index, index + 1), 16) < 128 then
                index = index + 2
                break
            end
            index = index + 2
        end
    end

    -- parse bytes balance = 2
    if string.sub(proto, index, index + 1) == "12" then
        index = index + 2
        -- calculate varint nb of bytes used to encode balance
        -- the balance is encoded with 32 bytes (0x20) maximum so the length takes a single byte
        balanceLength = tonumber(string.sub(proto, index, index + 1), 16) * 2
        assert(balanceLength <= 32, "Invalid balance length")
        index = index + balanceLength + 2
    end

    -- parse bytes codeHash = 3
    assert(string.sub(proto, index, index + 1) == "1a", "Invalid codeHash proto tag")
    index = index + 2;
    assert(string.sub(proto, index, index + 1) == "20", "Invalid codeHash length")
    index = index + 66;

    -- parse bytes storageRoot = 4
    assert(string.sub(proto, index, index + 1) == "22", "Invalid storageRoot proto tag")
    index = index + 2
    assert(string.sub(proto, index, index + 1) == "20", "Invalid storageRoot length");
    index = index + 2 -- start of storageRoot bytes
    -- extrack storageRoot
    storageRoot = "0x"..string.sub(proto, index, index + 63)
    return storageRoot
end

-- check if the ith bit is set in hex string bytes
-- @type    query
-- @param   bits (hex string) hex string without 0x
-- @param   i (uint) index of bit to check
-- @return  (bool) true if ith bit is 1
function bitIsSet(bits, i)
    require "bit"
    -- get the hex byte containing ith bit
    local byteIndex = math.floor(i/8)*2 + 1
    local byteHex = string.sub(bits, byteIndex, byteIndex + 1)
    local byte = tonumber(byteHex, 16)
    return bit.band(byte, bit.lshift(1,7-i%8)) ~= 0
end

-- compute the merkle proof verification
-- @type    query
-- @param   key (hex string) key for which the merkle proof is created
-- @param   leafHash (hex string) value stored in the smt
-- @param   ap ([] hex string without 0x) merkle proof nodes (audit path)
-- @param   keyIndex (uint) step counter in merkle proof iteration
-- @return  (0x hex string) hash of the smt root with given merkle proof
function verifyProof(key, leafHash, ap, keyIndex)
    if keyIndex == #ap then
        return leafHash
    end
    if bitIsSet(key, keyIndex) then
        local right = verifyProof(key, leafHash, ap, keyIndex+1)
        return crypto.sha256("0x"..ap[#ap-keyIndex]..string.sub(right, 3, #right))
    end
    local left = verifyProof(key, leafHash, ap, keyIndex+1)
    return crypto.sha256(left..ap[#ap-keyIndex])
end

-- Verify Aergo contract state inclusion Merkle proof
-- @type    query
-- @param   proto - (0x hex string) Proto bytes of the serialized contract account
-- @param   merkleProof ([]0x hex string) merkle proof of inclusion of protobuf serialized account in general trie
function verifyAergoStateProof(proto, merkleProof)
    local accountHash = crypto.sha256(proto)
    local leafHash = crypto.sha256(_destinationBridgeKey:get()..string.sub(accountHash, 3)..string.format('%02x', 256-#merkleProof))
    return _anchorRoot:get() == verifyProof(string.sub(_destinationBridgeKey:get(), 3), leafHash, merkleProof, 0)
end

-- Create a new bridge contract
-- @type    __init__
-- @param   validators ([]address) array of Aergo addresses
-- @param   bridge (address) address of already deployed bridge contract
-- @param   destinationBridgeKey (0x hex string) trie key of destination bridge contract in Aergo state trie
-- @param   tAnchor (uint) anchoring periode on this contract
-- @param   tFinal (uint) finality of anchored chain
-- @return  (string) id of contract
function constructor(validators, bridge, destinationBridgeKey, tAnchor, tFinal)
    _nonce:set(0)
    _validatorsCount:set(#validators)
    for i, addr in ipairs(validators) do
        _typecheck(addr, 'address')
        _validators[i] = addr
    end
    _bridge:set(bridge)
    _destinationBridgeKey:set(destinationBridgeKey)
    _tAnchor:set(tAnchor)
    _tFinal:set(tFinal)
    _anchorRoot:set("constructor")
    _anchorHeight:set(0)
    -- contractID is the hash of system.getContractID (prevent replay between contracts on the same chain) and system.getPrevBlockHash (prevent replay between sidechains).
    -- take the first 16 bytes
    local id = crypto.sha256(system.getContractID()..system.getPrevBlockHash())
    id = string.sub(id, 3, 34)
    _contractId:set(id)
    return id
end

-- Getter for validators
-- @type    query
-- @return  ([]string) array or validator addresses
function getValidators()
    local validators = {}
    for i=1, _validatorsCount:get() do
        validators[i] = _validators[i]
    end
    return validators
end

-- Getter for anchored state root and height
-- @type    query
-- @return  (0x hex string, int) state root, height of the anchored blockchain
function getForeignBlockchainState()
    return _anchorRoot:get(), _anchorHeight:get()
end

-- Register a new set of validators
-- @type    call
-- @param   validators ([]address) array of Aergo addresses
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @event   validatorsUpdate(proposer)
function validatorsUpdate(validators, signers, signatures)
    oldNonce = _nonce:get()
    -- it is safe to join validators without a ',' because the validators length is checked in _typecheck
    message = crypto.sha256(join(validators)..tostring(oldNonce).._contractId:get().."V")
    assert(validateSignatures(message, signers, signatures), "Failed new validators signature validation")
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

-- Replace the oracle with another one
-- @type    call
-- @param   newOracle (address) Aergo address of the new oracle
function oracleUpdate(newOracle, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(newOracle..tostring(oldNonce).._contractId:get().."O")
    assert(validateSignatures(message, signers, signatures), "Failed new oracle signature validation")
    _nonce:set(oldNonce + 1)
    contract.call(_bridge:get(), "oracleUpdate", newOracle)
end

-- Register new anchoring periode
-- @type    call
-- @param   tAnchor (uint) new anchoring periode
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
function tAnchorUpdate(tAnchor, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(tostring(tAnchor)..tostring(oldNonce).._contractId:get().."A")
    assert(validateSignatures(message, signers, signatures), "Failed tAnchor signature validation")
    _nonce:set(oldNonce + 1)
    _tAnchor:set(tAnchor)
    contract.call(_bridge:get(), "tAnchorUpdate", tAnchor)
end

-- Register new finality of anchored chain
-- @type    call
-- @param   tFinal (uint) new finality of anchored chain
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
function tFinalUpdate(tFinal, signers, signatures)
    oldNonce = _nonce:get()
    message = crypto.sha256(tostring(tFinal)..tostring(oldNonce).._contractId:get().."F")
    assert(validateSignatures(message, signers, signatures), "Failed tFinal signature validation")
    _nonce:set(oldNonce + 1)
    _tFinal:set(tFinal)
    contract.call(_bridge:get(), "tFinalUpdate", tFinal)
end

-- Register a new state anchor
-- @type    call
-- @param   root (0x hex string) Aergo bridge storage root
-- @param   height (uint) block height of root
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
function newStateAnchor(root, height, signers, signatures)
    assert(height > _anchorHeight:get() + _tAnchor:get(), "Next anchor height not reached")
    oldNonce = _nonce:get()
    -- NOTE since length of root is not checked, ',' is necessary before height
    message = crypto.sha256(string.sub(root, 3)..','..tostring(height)..tostring(oldNonce).._contractId:get().."R")
    assert(validateSignatures(message, signers, signatures), "Failed signature validation")
    _nonce:set(oldNonce + 1)
    _anchorRoot:set(root)
    _anchorHeight:set(height)
    contract.event("newAnchor", system.getSender(), height, root)
end

-- Register a new bridge anchor
-- @type    call
-- @param   proto - (0x hex string) Proto bytes of the serialized contract account
-- @param   merkleProof ([]0x hex string) merkle proof of inclusion of protobuf serialized account in general trie
function newBridgeAnchor(proto, merkleProof)
    local root = parseRootFromProto(proto)
    if not verifyAergoStateProof(proto, merkleProof) then
        error("Failed to verify bridge contract protobuf merkle proof")
    end
    contract.call(_bridge:get(), "newAnchor", root, _anchorHeight:get())
end

-- Register a new state anchor and update the bridge anchor
-- @type    call
-- @param   stateRoot (0x hex string) Aergo state root
-- @param   height (uint) block height of root
-- @param   signers ([]uint) array of signer indexes
-- @param   signatures ([]0x hex string) array of signatures matching signers indexes
-- @param   proto - (0x hex string) Proto bytes of the serialized contract account
-- @param   merkleProof ([]0x hex string) merkle proof of inclusion of protobuf serialized account in general trie
function newStateAndBridgeAnchor(stateRoot, height, signers, signatures, proto, merkleProof)
    newStateAnchor(stateRoot, height, signers, signatures)
    newBridgeAnchor(proto, merkleProof)
end

abi.register(validateSignatures, join, parseRootFromProto, bitIsSet, verifyProof, verifyAergoStateProof, getValidators, getForeignBlockchainState, validatorsUpdate, oracleUpdate, tAnchorUpdate, tFinalUpdate, newStateAnchor, newBridgeAnchor, newStateAndBridgeAnchor)
