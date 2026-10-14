---
Record: DDR-0004
Title: Generator recipes, pinned digests, and bounded hydration
Status: Proposed
Date: 2026-10-14
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0004: Generator recipes, pinned digests, and bounded hydration

## Context

Exhaustive truth tables are too large to commit (DDR-0001). Scalar
resolution across every case variant, position, style, and tag is about 41,000
cases. They must still be exactly reproducible, reviewable, and detectably
unchanged between releases, and producing them must never write unbounded
output or touch the checkout.

## Decision

1. **A recipe** (`recipes/<format>/<id>.r<N>.json`, `recipe/v1`) names a
   reviewed generator under `generators/<format>/`, its parameters, the profile
   its expectations belong to, classification and provenance (synthetic only),
   caps (`max_cases`, `max_output_bytes` within its tier), and the **expected
   output**: case count, total input bytes, and a digest.
2. **The digest** is `sha256` over the recipe's case records, each serialized
   canonically (ADR-0002) and followed by a newline, in generation order. A
   change to any input byte, expectation, classification, or ordering changes
   the digest.
3. **Generated case IDs** are `<recipe id>.<local id>`. The case revision is the
   recipe revision. Changing any expectation requires a new recipe revision;
   the old one stays reproducible from history.
4. **`hydrate`** writes generated inputs and a canonical case manifest into a
   new output root:
   - it refuses a root that exists, lies inside the checkout, or contains it;
   - it enforces per-recipe caps and the tier's aggregate cap, counting both
     input and manifest bytes, while it writes;
   - it builds in a temporary sibling directory and renames it into place only
     after every recipe's count, bytes, and digest match the recorded values;
   - on any failure it removes only the temporary directory it created, and
     never deletes a path the caller supplied;
   - a completion marker is written last, so an interrupted run is never
     mistaken for a complete one.
5. **`verify`** rechecks a hydrated root: the marker, each input's hash and
   length, canonical manifest lines, and each recipe's digest against the
   checkout's recipe.
6. **Generators** are Python 3.9 standard library, deterministic, and free of
   time, randomness, environment, and set-order dependence (ADR-0002). They
   receive only the recipe's parameters.

## Consequences

- Consumers pin a corpus commit and get exact, verifiable inputs and
  expectations without committing megabytes of tables.
- Recorded digests come from a reviewed generator. They show the output has not
  changed, not that it is correct. Correctness rests on independent review of
  the generator and its hand-checked boundary goldens, and a recipe stays
  `provisional` until that review is done.
- Hydrated manifests repeat recipe-level fields in every case, which makes the
  conformance tier's manifest about 58 MB. That size is within the tier cap.
  Moving shared fields to the recipe is a possible later schema revision.
