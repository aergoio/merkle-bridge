.PHONY: docker compile deploy bridge transfer_to_destination

docker:
	docker run -d -p 7845:7845 aergo/node aergosvr --testmode --config /aergo/config.toml
	docker run -d -p 8845:7845 aergo/node aergosvr --testmode --config /aergo/config.toml

compile:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bytecode.txt

deploy:
	python3 bridge_operator/deployer.py

bridge:
	python3 bridge_operator/operator.py


transfer_to_destination:
	python3 wallet/wallet.py
