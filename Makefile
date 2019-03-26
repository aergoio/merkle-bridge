.PHONY: install compile_bridge compile_token deploy_bridge proposer validator broadcaster protoc wallet deploy_token docker 

install:
	pip install git+ssh://git@github.com/aergoio/herapy.git@bff87a752403216443d5bf7ff52fc2fd671da44e
	pip install pytest

compile_bridge:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bridge_bytecode.txt

compile_token:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/standard_token.lua > contracts/token_bytecode.txt

deploy_bridge:
	python3 -m bridge_operator.bridge_deployer

proposer:
	python3 -m bridge_operator.proposer_client

validator:
	python3 -m bridge_operator.validator_server

broadcaster:
	python3 -m broadcaster.broadcaster_server

protoc:
	python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=. \
		--grpc_python_out=. \
		./proto/bridge_operator/*.proto
	python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=. \
		--grpc_python_out=. \
		./proto/broadcaster/*.proto


#Below commands are simple tools for development only
wallet:
	python3 -m wallet.wallet

deploy_token:
	python3 -m wallet.token_deployer

docker:
	docker run --rm -d -p 7845:7845 aergo/node aergosvr --config /aergo/testmode.toml
	docker run --rm -d -p 8845:7845 aergo/node aergosvr --config /aergo/testmode.toml
