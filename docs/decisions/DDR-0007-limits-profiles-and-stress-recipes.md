---
Record: DDR-0007
Title: Explicit-limits profiles, recipe hazards and budgets, and listing
Status: Proposed
Date: 2026-10-15
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0007: Explicit-limits profiles, recipe hazards and budgets, and listing

## Context

Adversarial families (alias expansion, depth, many keys, long scalars,
late failures) need expectations at resource limits: one below, at, and one
above each limit. The yamlprims specification gives proposed default limits
it describes as unmeasured. Expectations tied to those defaults would change
whenever the defaults did, and boundary inputs at an 8 MiB or depth-128 limit
are large. Hazardous generated cases also need per-case execution budgets for
the containment runner (SecDR-0002), and maintainers need to see what each
tier will produce before hydrating it.

## Decision

1. **Profiles may carry explicit `limits`,** named exactly as the cited
   specification's `Limits` fields (all twelve, no others). They are
   validated by that specification's own rules:
   - every limit is an integer ≥ 1;
   - `max_depth` ≤ 255;
   - `max_scalar_bytes` and `max_key_bytes` ≤ `max_owned_bytes`.

   A profile without `limits` uses whatever its cited specification says.
2. **`yamlprims-core-limits` r1** is `yamlprims-core` r2 (specification 1.1)
   with small explicit limits: depth 8, 64 nodes, 8 alias events, and 8 KiB
   owned bytes, among others. Limit-boundary expectations are computed from
   the specification's arithmetic for these values, so boundary inputs stay
   small and expectations do not depend on proposed defaults.
3. **Recipes declare `hazards` and per-case `budgets`** (wall time, memory,
   output). A recipe with hazards must declare budgets. Generated cases
   inherit the recipe's tier, hazards, and budgets, as committed hazardous
   cases already must. Recipes without hazards produce unchanged records, so
   existing digests are unaffected.
4. **`corpus.py list`** reports recipes and committed cases for a tier and
   below, with case counts and input bytes. `--show-budgets` generates the
   recipes to report total output bytes against the tier cap. `--json`
   emits canonical JSON.
5. **The stress tier is hydrated only when requested.** Stress recipes are
   never part of smoke or conformance hydration, so `make hydrate`
   (conformance) is unaffected by how large the stress ladders grow.

## Consequences

- The hazardous recipes in the next stage can state limit expectations on
  small inputs, and the runner gets per-case budgets from the records
  themselves.
- Changing a limits profile's values is a new profile revision, like any
  other expectation change.
