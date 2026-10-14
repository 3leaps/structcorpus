---
Record: PDR-0002
Title: goneat as the maintainer format, lint, and schema toolchain
Status: Proposed
Date: 2026-10-14
Owner: devlead (drafting); acceptance by the maintainer
---

# PDR-0002: goneat as the maintainer format, lint, and schema toolchain

## Context

ADR-0002 keeps the corpus usable with nothing but `python3`. Maintainers
still need consistent formatting and linting for the Python tools, YAML
configuration, workflows, and shell scripts, plus full JSON Schema validation.
They need all of it without a Python package manager, and without any risk to
byte-exact fixtures (DDR-0001).

[goneat](https://github.com/fulmenhq/goneat) wraps established tools (ruff,
yamllint, yamlfmt, shfmt, actionlint, checkmake) under one assessment command,
and it validates JSON Schemas against embedded meta-schemas offline. A
digest-pinned runner image provides the same toolchain in CI.

## Decision

1. **`make` targets are the interface:** `fmt`, `fmt-check`, `lint`, `schemas`,
   `test`, `validate`, `hydrate`, and `check` (all non-mutating checks).
   `fmt`, `fmt-check`, `lint`, and `schemas` call goneat. The rest need only
   `python3`.
2. **Configuration lives in the repository:** `.goneat/assess.yaml`,
   `.goneatignore`, `.yamllint`, `.yamlfmt`, and `ruff.toml`. Ruff lints for
   correctness (pycodestyle errors and warnings, pyflakes, bugbear, imports)
   and formats. Its target version is the Python 3.9 floor.
3. **Byte-exact trees are excluded from every tool.** `fixtures/` and
   `expected/` are listed in `.goneatignore` and in each tool's own exclusion
   list. Negative schema controls are excluded too, because they are invalid
   by design. CI records fixture hashes, runs `make fmt`, and fails if any
   fixture byte or any tracked file changes.
4. **CI runs goneat in the digest-pinned goneat tools runner image**, which
   bundles goneat and the wrapped tools. Nothing is installed at CI time, and
   no Python package manager is involved.
5. **Corpus users are unaffected.** goneat and ruff are maintainer
   requirements only. Validating, hydrating, and verifying a pinned corpus
   still needs only `python3` (ADR-0002).

## Consequences

- One command applies the repository's whole formatting and lint policy, the
  same way locally and in CI.
- Changing the runner image is a reviewed change, just like any other pin.
- A maintainer without goneat can still run `test`, `validate`, and
  `hydrate`. `fmt`, `lint`, and `schemas` need goneat, or they can be left to
  CI.
