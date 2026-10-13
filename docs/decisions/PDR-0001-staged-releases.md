---
Record: PDR-0001
Title: Staged releases, each with its own acceptance list
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
---

# PDR-0001: Staged releases, each with its own acceptance list

## Context

The full target is every YAML adversarial family, seven bounded generator
recipes, a verified containment runner, Windows/Linux byte parity, mutation
checks, and an upstream-suite import. Gating the first release on all of
that would delay any useful corpus far longer than the corpus helps.
Reviewed synthetic material already exists and can ship sooner.

## Decision

| Stage | Contents | Consumers and tiers |
| --- | --- | --- |
| **0.1** | Foundation: policy, decision records, schemas, validator with negative and mutation tests, byte-preservation rules. Migrated reviewed synthetic material: scalar/duplicate-key truth generator with pinned hashes and counts, hand-checked goldens, wire cases, negatives. | One consumer driver; smoke and conformance tiers only |
| **0.2** | Every YAML adversarial family, the seven bounded recipes, hydration with output caps, stress tier with a verified containment runner (SecDR-0002) | Stress tier added |
| **0.3** | Pinned yaml-test-suite import with retained notices and upstream IDs; full Windows/Linux parity matrix | Broader engines and bindings |

Fuzz-seed promotion, JSON, and XML follow when a consumer commits to them.

Each stage publishes its own acceptance list in the release notes. Every
list includes, at minimum:

- every shipped case validates, with no non-public classification and no
  dangling reference;
- negative validator tests pass;
- two fresh hydrations are byte-identical;
- the consumer reports pass, expected policy difference, mismatch, and
  unexecuted coverage separately;
- unresolved `provisional` expectations are listed.

A corpus release does not require any consumer to pass every case.

## Consequences

- 0.1 can ship while coverage is known to be partial. `docs/coverage.md`
  lists implemented, planned, and unsupported families, so the gap stays
  visible.
- Later stages may tighten the schema. Breaking schema changes are stated
  explicitly, and old case revisions are never overwritten.
