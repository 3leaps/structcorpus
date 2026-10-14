# structcorpus developer targets. Tooling: python3 (3.9+) for the corpus;
# goneat for format, lint, and JSON Schema checks.
.PHONY: all help check test validate schemas hydrate fmt fmt-check lint clean

PYTHON ?= python3
GONEAT ?= goneat

all: check

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

check: fmt-check lint validate test schemas hydrate ## Run every non-mutating check

test: ## Run the corpus-tool unit tests
	$(PYTHON) -m unittest discover -s tests

validate: ## Check repository, metadata, case, and recipe rules
	$(PYTHON) tools/corpus.py validate

schemas: ## Meta-validate schemas, then validate metadata and negative controls
	$(GONEAT) schema validate-schema --schema-id json-schema-draft-07 schemas/*.json
	tools/schema-check.sh

hydrate: ## Hydrate the conformance tier twice and require identical bytes
	$(PYTHON) tools/hydrate-twice.py conformance

fmt: ## Apply formatting (fixtures and expected are excluded)
	$(GONEAT) assess --categories format --fix --ci-summary

fmt-check: ## Verify formatting without modifying files
	$(GONEAT) assess --categories format --mode check --fail-on low --ci-summary

lint: ## Run goneat lint (ruff, yamllint, actionlint, shfmt, checkmake)
	$(GONEAT) assess --categories lint --mode check --fail-on low --ci-summary

clean: ## Remove Python and tool caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .ruff_cache
