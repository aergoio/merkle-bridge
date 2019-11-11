.PHONY: compile_bridge compile_oracle compile_token deploy_test_bridge proposer validator protoc docker clean tests

# Shortcuts for development and testing

compile_bridge:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bridge_bytecode.txt

compile_oracle:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/oracle.lua > contracts/oracle_bytecode.txt

compile_token:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/standard_token.lua > contracts/token_bytecode.txt

deploy_test_bridge:
	python3 -m aergo_bridge_operator.bridge_deployer -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --local_test
	python3 -m aergo_bridge_operator.oracle_deployer -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --local_test
	python3 -m aergo_wallet.token_deployer

proposer:
	python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --local_test

validator:
	python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --local_test

protoc:
	python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=. \
		--grpc_python_out=. \
		./proto/aergo_bridge_operator/*.proto

docker:
	# docker build --build-arg GIT_TAG=5a16373a3c535f77304709f725e10284dccfbea1 -t aergo/node ./docker
	docker-compose -f ./docker/docker-compose.yml up

clean:
	rm -fr docker/*/data
	docker-compose -f ./docker/docker-compose.yml down

tests:
	python3 -m pytest -s tests