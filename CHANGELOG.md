# Changelog

## [Unreleased]

- `make release-prepare-tag-message` drafts a new tag message from the release's dated `CHANGELOG.md` section, copied as written after the changelog passes its release guard. The draft carries a review-marker line that tagging refuses until it is deleted.

## [0.1.0] - 2026-11-23

First signed release.

- YAML 1.2.2 corpus: 103 static cases in `manifests/yaml/cases.jsonl` with byte-exact inputs under `fixtures/yaml/`, and 33 pinned recipes under `recipes/yaml/` that generate the rest. `tools/corpus.py list` counts 61,366 cases through the conformance tier and 61,399 through the stress tier.
- Profiles under `manifests/yaml/profiles/` through specification 1.5, with format-level event expectations kept apart from profile-level value, budget, and limit expectations.
- `tools/corpus.py` validates the repository, aggregates the per-format case shards, hydrates tiers outside the checkout with digest verification, verifies hydrated output, lists tier contents, and prints canonical JSON. It needs only the Python 3.9+ standard library.
- Per-format layout: `manifests/formats.json` declares each format's registries; YAML registries live under `manifests/yaml/`.
- Releases are signed annotated tags verified against the public key committed in the tagged commit. See `docs/security/README.md`.

[Unreleased]: https://github.com/3leaps/structcorpus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/3leaps/structcorpus/releases/tag/v0.1.0
