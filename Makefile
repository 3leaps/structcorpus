# structcorpus developer targets. Tooling: python3 (3.9+) for the corpus;
# goneat for format, lint, and JSON Schema checks.
.PHONY: all help check prepush stress-selftest test validate aggregate schemas hydrate fmt fmt-check lint clean
.PHONY: content-check surface-scan surface-scan-ci surface-scan-release pr-final
.PHONY: release-github-preflight release-preflight release-guard-tag-name release-guard-tag-version release-guard-signing-tag
.PHONY: release-guard-release-surfaces sync-changelog-links release-prepare-tag-message release-tag release-push-tag
.PHONY: release-verify-tag release-verify-published-tag release-verify-remote-tag release-export-pin release-validate-pin
.PHONY: release-insert-anchors release-anchors-check release-tooling-test

PYTHON ?= python3
GONEAT ?= goneat
VERSION := $(shell cat VERSION)

all: check

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

check: fmt-check lint validate test schemas hydrate ## Run every non-mutating check

prepush: check stress-selftest ## Pre-push and PR-final gate: check, then the containment self-test

stress-selftest: ## Prove container limits are enforced; fails fast if the runtime is not started
	$(PYTHON) tools/runner.py selftest --require-containment

test: ## Run the corpus-tool unit tests
	$(PYTHON) -m unittest discover -s tests

validate: ## Check repository, metadata, case, and recipe rules (never writes)
	$(PYTHON) tools/corpus.py validate

aggregate: ## Regenerate manifests/cases.jsonl from the per-format case shards
	$(PYTHON) tools/corpus.py aggregate

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

content-check: ## Verify committed files contain no local paths, keys, tokens, or commit markers
	$(PYTHON) -I -B ./scripts/content-check.py

surface-scan: content-check ## Public-surface scan, PR scope (skips the catalog tier when LIMENSAFE_CATALOG_PATH is unset)
	@STRUCTCORPUS_SURFACE_SCOPE=pr ./scripts/surface-scan.sh

surface-scan-ci: ## Public-surface scan, PR scope, built-in baseline only (CI; no catalog)
	@STRUCTCORPUS_SURFACE_BASELINE_ONLY=1 STRUCTCORPUS_SURFACE_SCOPE=pr ./scripts/surface-scan.sh

surface-scan-release: content-check ## Public-surface scan, release scope (requires the external catalog)
	@STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1 STRUCTCORPUS_SURFACE_SCOPE=release ./scripts/surface-scan.sh

pr-final: check ## Maintainer PR gate: check plus the required PR-scope surface scan (needs LIMENSAFE_CATALOG_PATH, STRUCTCORPUS_SURFACE_PR_TEXT)
	@STRUCTCORPUS_SURFACE_SCOPE=pr STRUCTCORPUS_SURFACE_SCAN_REQUIRED=1 ./scripts/surface-scan.sh

# Signed-tag release ceremony. Releases are source-only signed tags; see
# RELEASE_CHECKLIST.md. Flow: release-preflight -> release-prepare-tag-message
# -> release-tag (local, signed, verified) -> release-push-tag ->
# release-verify-published-tag. The tag targets read STRUCTCORPUS_RELEASE_TAG,
# STRUCTCORPUS_TAG_MESSAGE_DIR, STRUCTCORPUS_TAGGER_NAME, STRUCTCORPUS_TAGGER_EMAIL,
# STRUCTCORPUS_GPG_SIGNING_FINGERPRINT, STRUCTCORPUS_PGP_KEY_ID (<subkey>!),
# STRUCTCORPUS_GPG_HOMEDIR and STRUCTCORPUS_DECERNOR_BIN.

release-github-preflight: ## Verify the remote tag-protection ruleset and immutable releases
	@./scripts/release-github-preflight.sh

release-preflight: ## Pre-tag gate: clean synced main, changelog, pins, dates, and release surface scan
	@./scripts/release-verify-committed-anchors.sh
	@$(MAKE) --no-print-directory surface-scan-release
	@./scripts/release-preflight.sh

release-guard-tag-name: ## Guard: STRUCTCORPUS_RELEASE_TAG set and canonical vX.Y.Z (no VERSION check)
	@if [ -z "$(STRUCTCORPUS_RELEASE_TAG)" ]; then \
		echo "STRUCTCORPUS_RELEASE_TAG not set (example: STRUCTCORPUS_RELEASE_TAG=v$(VERSION))." >&2; \
		exit 1; \
	fi
	@printf '%s\n' "$(STRUCTCORPUS_RELEASE_TAG)" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$$' || { \
		echo "STRUCTCORPUS_RELEASE_TAG must be canonical vX.Y.Z" >&2; exit 1; }
	@echo "[ok] release tag name $(STRUCTCORPUS_RELEASE_TAG) is canonical"

release-guard-tag-version: ## Guard: STRUCTCORPUS_RELEASE_TAG canonical and matches VERSION
	@if [ -z "$(STRUCTCORPUS_RELEASE_TAG)" ]; then \
		echo "STRUCTCORPUS_RELEASE_TAG not set (example: STRUCTCORPUS_RELEASE_TAG=v$(VERSION))." >&2; \
		exit 1; \
	fi
	@STRUCTCORPUS_RELEASE_TAG="$(STRUCTCORPUS_RELEASE_TAG)" ./scripts/release-guard-tag-version.sh

release-guard-signing-tag: release-guard-tag-version ## Guard: STRUCTCORPUS_RELEASE_TAG matches VERSION
	@:

release-guard-release-surfaces: ## Verify CHANGELOG.md section and compare links match VERSION
	@./scripts/release-guard-release-surfaces.sh

sync-changelog-links: ## Sync CHANGELOG compare-link footers to VERSION
	@./scripts/sync-changelog-links.sh

release-prepare-tag-message: ## Maintainer-only: prepare and review the external per-cut tag message
	@./scripts/release-tag-operator.sh prepare-message

release-tag: ## Maintainer-only: create and verify a local signed version tag (no push)
	@./scripts/release-tag-operator.sh local-tag

release-push-tag: ## Maintainer-only: publish and verify the signed version tag
	@./scripts/release-tag-operator.sh remote-push

release-verify-tag: ## Verify the local tag using only the committed public pin
	@./scripts/release-verify-tag.sh

# The published-tag check installs the remote tag as the local ref only after
# every check passes.
release-verify-published-tag: release-guard-tag-name ## Verify the published tag object and signature against its committed pin
	@STRUCTCORPUS_RELEASE_TAG="$(STRUCTCORPUS_RELEASE_TAG)" ./scripts/release-verify-published-tag.sh

release-verify-remote-tag: ## Compare local and remote tag objects and GitHub verification
	@./scripts/release-verify-remote-tag.sh

release-export-pin: ## Maintainer-only: export the approved public key when no pin exists
	@./scripts/release-export-pin.sh

release-validate-pin: ## Maintainer-only: read-only validation of the existing public pin
	@./scripts/release-validate-pin.sh

release-insert-anchors: release-validate-pin ## Maintainer-only: validate pin, then generate absent public anchors
	@./scripts/release-insert-anchors.sh

release-anchors-check: ## Check the committed public key against both fingerprint anchors (needs gpg, STRUCTCORPUS_DECERNOR_BIN)
	@./scripts/release-verify-committed-anchors.sh
	@./scripts/validate-release-anchors.sh

release-tooling-test: ## Run the release and surface-hygiene tooling test suites (throwaway keys; needs gpg, git, python3, jq, make, decernor)
	@./scripts/release-tooling-test.sh
