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
	python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --privkey_name "proposer" --privkey_pwd "1234" --anchoring_on --auto_update --oracle_update

validator:
	python3 -m aergo_bridge_operator.validator_server -c './test_config.json' --net1 'mainnet' --net2 'sidechain2' --validator_index 1 --privkey_name "validator" --local_test

protoc:
	python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=. \
		--grpc_python_out=. \
		./proto/aergo_bridge_operator/*.proto

docker:
	# docker build --build-arg GIT_TAG=3f24ea32ddeb27dd1b86671d1622ab2108a1f42e -t aergo/node ./docker
	docker-compose -f ./docker/docker-compose.yml up

clean:
	rm -fr docker/*/data
	docker-compose -f ./docker/docker-compose.yml down

tests:
	python3 -m pytest -s tests

monitor:
	python3 -m aergo_bridge_operator.proposer_client -c './test_config.json' --net1 'mainnet' --net2 'sidechain2'

lint:
	# ignote bare except E722 in proposer, ignore W503 as it will be considered best practice
	flake8 \
		--exclude=*_pb2_grpc.py,*_pb2.py \
		--ignore=E722,W503 \
		aergo_bridge_operator aergo_wallet aergo_cli

mypy:
	mypy -p aergo_bridge_operator -p aergo_wallet -p aergo_cli