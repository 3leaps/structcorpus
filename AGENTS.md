# structcorpus — AI Agent Guide

## Safety header (read first)

**This repository is public, and every committed byte is admitted as
`0-public`.** Before adding or changing anything, read
[SecDR-0001](docs/decisions/SecDR-0001-public-only-admission.md).

- Never derive a fixture from a real file, even if you rename or redact it.
  Recreate the behavior as a minimal synthetic case.
- Never name a non-public repository, branch, commit, product, person, or
  internal process anywhere: fixtures, manifests, comments, generator source,
  commit messages, or PR text.
- Never add an `unknown/`, `pending/`, or intake directory.
- This repository never references its consumers. Consumers pin it.

This is a **security-sensitive** repository in the sense of the crucible
decision-record catalog. SecDRs here are public and describe controls only.

Some fixtures are deliberately hostile inputs: alias bombs, deep nesting,
huge scalars. Do not run them through a parser outside the bounded runner
([SecDR-0002](docs/decisions/SecDR-0002-bounded-execution-containment.md)).

## Before changing behavior

- `README.md`
- `docs/decisions/` (index in `docs/decisions/README.md`)
- `docs/admission.md` before touching cases
- `docs/coverage.md` when adding or completing coverage

If local guidance exists for this repository, read it as well.

## Development

```sh
make check        # everything non-mutating: format, lint, validate, tests, schemas, hydrate
make fmt          # apply formatting (fixtures/ and expected/ are never touched)
make test validate hydrate   # python3 only, no goneat needed
make prepush      # before pushing or marking a PR final: check + containment self-test
```

- Maintainer tooling is goneat with ruff, yamllint, yamlfmt, shfmt, actionlint,
  and checkmake (PDR-0002). CI runs it in a digest-pinned runner image.

- After editing a fixture, recompute its `sha256` and `bytes` in
  `manifests/cases.jsonl`. Never edit a fixture to match an expectation.
- New cases start `provisional`. Only a reviewer distinct from the author
  marks one `reviewed`.

- Tooling is Python 3.9+ standard library only. Do not add a package
  manager, requirements file, or third-party import (ADR-0002).
- Metadata is JSON or JSONL and must contain no duplicate keys.
- Never open fixture files in an editor or formatter that rewrites bytes.
- Hydration and run output go to a directory outside this checkout.

## Decision records

Follow the crucible `*DR` taxonomy (`<TYPE>-<NNNN>-<slug>.md`, numbered
per type across the whole repository). Implementers draft records as
`Proposed`; only the maintainer accepts them.

## Rules of the road

- Work on a feature branch and open a PR to protected `main`.
- Public commit and PR text describes the change only. Keep planning codes
  and rationale out of it.
- Attribution: every commit message and PR body ends with:

  ```text
  Role: <bare role slug>
  Co-authored-by: <model> <noreply@3leaps.net>
  Committer-of-Record: @3leapsdave
  ```
