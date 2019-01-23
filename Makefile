.PHONY: docker compile_bridge compile_token deploy_bridge deploy_token bridge transfer_to_sidechain transfer_from_sidechain proposer validator

docker:
	docker run --rm -d -p 7845:7845 aergo/node aergosvr --config /aergo/testmode.toml
	docker run --rm -d -p 8845:7845 aergo/node aergosvr --config /aergo/testmode.toml
	

compile_bridge:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bridge_bytecode.txt

compile_token:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/standard_token.lua > contracts/token_bytecode.txt

deploy_bridge:
	python3 bridge_operator/bridge_deployer.py

deploy_token:
	python3 wallet/token_deployer.py

bridge:
	python3 bridge_operator/operator.py

transfer_to_sidechain:
	python3 wallet/transfer_to_sidechain.py

transfer_from_sidechain:
	python3 wallet/transfer_from_sidechain.py

proposer:
	python3 bridge_operator/proposer_client.py

validator:
	python3 bridge_operator/validator_server.py
