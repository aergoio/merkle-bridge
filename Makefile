.PHONY: compile deploy

compile:
	$(GOPATH)/src/github.com/aergoio/aergo/bin/aergoluac --payload contracts/merkle_bridge.lua > contracts/bytecode.txt

deploy:
	python3 bridge_operator/operator.py
