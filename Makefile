.PHONY: test safety-check tofu-validate verify

test:
	python3 -m pytest

safety-check:
	PYTHONPATH=src python3 -m merry_runtime.jobs validate-hermes-profile
	PYTHONPATH=src python3 -m merry_runtime.jobs list-mcp-tools

tofu-validate:
	tofu -chdir=infra/terraform fmt -check
	TF_DATA_DIR=/tmp/hermes-merry-tofu tofu -chdir=infra/terraform init -backend=false
	TF_DATA_DIR=/tmp/hermes-merry-tofu tofu -chdir=infra/terraform validate

verify: test safety-check tofu-validate
