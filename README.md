# structcorpus

Public, reproducible test material for structured-document readers and their
language bindings. YAML comes first; JSON and XML namespaces are reserved
until a consumer needs them.

structcorpus holds the inputs, the expected properties, the provenance
records, and the generators. It does not contain a parser. Each consumer
writes a small driver that runs its own API against a pinned corpus release.

## Principles

- **Public only.** Every case is synthetic, or comes from a public source with
  documented redistribution rights. Nothing is derived from private data, and
  redacted or blinded material is never admitted. See
  [SecDR-0001](docs/decisions/SecDR-0001-public-only-admission.md) and
  [docs/admission.md](docs/admission.md).
- **Format truth is kept apart from adapter policy.** Format-level event
  streams can be checked against any engine. Value trees, budgets, and
  resource accounting appear only under a named, versioned profile. See
  [DDR-0002](docs/decisions/DDR-0002-format-events-and-profile-expectations.md).
- **Byte-exact fixtures.** Git never rewrites line endings under `fixtures/`,
  `expected/`, or the case shards under `manifests/`. See
  [DDR-0001](docs/decisions/DDR-0001-byte-exact-fixture-storage.md).
- **Nothing to install beyond `python3`.** The tools use only the Python 3.9+
  standard library; there is no package manager and no virtual environment.
  See [ADR-0002](docs/decisions/ADR-0002-python-stdlib-tooling.md).
- **Bounded execution.** Hostile cases run only under enforced limits.
  See [SecDR-0002](docs/decisions/SecDR-0002-bounded-execution-containment.md).

## Usage

```sh
python3 tools/corpus.py validate          # repository, metadata, and case rules
python3 tools/corpus.py aggregate         # regenerate manifests/cases.jsonl from the format shards
python3 tools/corpus.py hydrate --tier conformance --output /tmp/structcorpus-out
python3 tools/corpus.py verify --root /tmp/structcorpus-out
python3 tools/corpus.py canon FILE.json   # canonical (JCS) form of a metadata file
python3 tools/corpus.py list --tier stress --show-budgets   # what each tier contains
```

Maintainers run `make check` for everything non-mutating: formatting, lint,
JSON Schema validation, tests, and a double hydration. Format, lint, and
schema checks use [goneat](https://github.com/fulmenhq/goneat)
([PDR-0002](docs/decisions/PDR-0002-goneat-maintainer-toolchain.md)). Consumers
need only `python3`.

Before pushing, maintainers run `make prepush`. It adds a containment
self-test that needs a container runtime ([docs/running.md](docs/running.md)).

Large tables are generated, not committed: each recipe under `recipes/` pins
its generator, parameters, case count, and a digest of the exact output
([DDR-0004](docs/decisions/DDR-0004-recipes-and-hydration.md)). Hydration
writes only to a new directory outside the checkout.

Each format's registries live under `manifests/<format>/`, and
`manifests/formats.json` declares their paths
([DDR-0014](docs/decisions/DDR-0014-per-format-manifest-layout.md)). YAML
cases live in `manifests/yaml/cases.jsonl` and reference inputs under
`fixtures/yaml/`. Profiles are in `manifests/yaml/profiles/`, and span
conventions are in `manifests/yaml/span-conventions/`. `manifests/cases.jsonl`
is the generated index of every format's static cases; regenerate it with
`python3 tools/corpus.py aggregate` after editing a shard. The record formats
are defined in
[DDR-0003](docs/decisions/DDR-0003-case-record-and-value-notation.md) and
`schemas/`.

See [PDR-0001](docs/decisions/PDR-0001-staged-releases.md) for the release
stages.

## Status

YAML 1.2.2 cases and recipes ship from `v0.1.0`; JSON and XML remain
reserved. Coverage is tracked in [docs/coverage.md](docs/coverage.md), and
changes in [CHANGELOG.md](CHANGELOG.md).

## Releases

Releases are signed annotated Git tags; nothing else is published. The
release identity, the explicit tag input, the pre-tag gate, and the CI check of
every published tag are described in
[PDR-0003](docs/decisions/PDR-0003-signed-tag-releases.md). The maintainer
procedure is [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Consuming

Pin a commit or release, together with its content hashes and the profile
revision. Never track `main`. Releases are signed annotated tags; verify them
against the key committed in the tagged commit as described in
[docs/security/README.md](docs/security/README.md).

## License

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or
[MIT license](LICENSE-MIT) at your option. See [NOTICE](NOTICE) for project
name and trademark notices. Material imported from public upstreams keeps
its own license and notices, recorded per case.
