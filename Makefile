.PHONY: docker compile_bridge compile_token deploy_bridge deploy_token bridge transfer_to_sidechain transfer_from_sidechain wallet proposer validator protoc

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
	python3 -m wallet.token_deployer

bridge:
	python3 bridge_operator/operator.py

transfer_to_sidechain:
	python3 -m wallet.transfer_to_sidechain

transfer_from_sidechain:
	python3 -m wallet.transfer_from_sidechain

wallet:
	python3 -m wallet.wallet

proposer:
	python3 bridge_operator/proposer_client.py

validator:
	python3 bridge_operator/validator_server.py

protoc: ## generate *_pb2.py and *_pb2_grpc.py in bridge_operator/grpc from bridge_operator/proto/*.proto
	python3 -m grpc_tools.protoc \
		-I./bridge_operator/proto \
		--python_out=./bridge_operator \
		--grpc_python_out=./bridge_operator \
		./bridge_operator/proto/*.proto
	#find ./aergo/herapy/grpc -type f -name '*_pb2.py' -exec sed -i '' -e 's/^import\(.*\)_pb2\(.*\)$$/from . import\1_pb2\2/g' {} \;
	#find ./aergo/herapy/grpc -type f -name '*_pb2_grpc.py' -exec sed -i '' -e 's/^import\(.*\)_pb2\(.*\)$$/from . import\1_pb2\2/g' {} \;

