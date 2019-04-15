.PHONY: install compile_bridge compile_token deploy_bridge proposer validator broadcaster protoc wallet deploy_token docker clean

install:
	pip install git+ssh://git@github.com/aergoio/herapy.git@4aabc7d2cb45cdbf263a972f6f11857c13118a87
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
	docker-compose -f ./docker/docker-compose.yml up

clean:
	rm -fr docker/*/data
	docker-compose -f ./docker/docker-compose.yml down
