.PHONY: install compile_bridge compile_token deploy_bridge proposer validator protoc wallet deploy_token transfer_to_sidechain transfer_from_sidechain update_validators docker 

install:
	pip install git+ssh://git@github.com/aergoio/herapy.git@d1cc62274a681b3c50deb5c883bb08b0a590cb1b
	pip install deprecated

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

protoc: ## generate *_pb2.py and *_pb2_grpc.py in bridge_operator/grpc from bridge_operator/proto/*.proto
	python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=. \
		--grpc_python_out=. \
		./proto/bridge_operator/*.proto
	#find ./aergo/herapy/grpc -type f -name '*_pb2.py' -exec sed -i '' -e 's/^import\(.*\)_pb2\(.*\)$$/from . import\1_pb2\2/g' {} \;
	#find ./aergo/herapy/grpc -type f -name '*_pb2_grpc.py' -exec sed -i '' -e 's/^import\(.*\)_pb2\(.*\)$$/from . import\1_pb2\2/g' {} \;


#Below commands are simple tools for development only
wallet:
	python3 -m wallet.wallet

deploy_token:
	python3 -m wallet.token_deployer

transfer_to_sidechain:
	python3 -m wallet.transfer_to_sidechain

transfer_from_sidechain:
	python3 -m wallet.transfer_from_sidechain

update_validators:
	python3 -m bridge_operator.update_validators

docker:
	docker run --rm -d -p 7845:7845 aergo/node aergosvr --config /aergo/testmode.toml
	docker run --rm -d -p 8845:7845 aergo/node aergosvr --config /aergo/testmode.toml
