.PHONY: docker compile_bridge compile_token deploy_bridge deploy_token bridge transfer_to_destination

docker:
	docker run -d -p 7845:7845 aergo/node aergosvr --testmode --config /aergo/config.toml
	docker run -d -p 8845:7845 aergo/node aergosvr --testmode --config /aergo/config.toml

compile_bridge:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bridge_bytecode.txt

compile_token:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/standard_token.lua > contracts/token_bytecode.txt

deploy_bridge:
	python3 bridge_operator/bridge_deployer.py

deploy_token:
	python3 bridge_operator/token_deployer.py

bridge:
	python3 bridge_operator/operator.py

transfer_to_destination:
	python3 wallet/wallet.py
