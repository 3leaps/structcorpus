---
Record: DDR-0006
Title: Profile and span-convention revisions for yamlprims specification 1.1
Status: Proposed
Date: 2026-10-14
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0006: Profile and span-convention revisions for yamlprims specification 1.1

## Context

The yamlprims specification moved from revision 1.0 (`spec-v1.0`) to revision
1.1 (`spec-v1.1`). The changes that matter to the corpus are:
- **1.1/E-1:** a block scalar's span now ends before its final line break;
- **1.1/E-2:** empty streams yield zero documents through multi-document
  entrypoints, explicit empty documents have defined roots, and a stream of
  two explicit empty documents returns two documents;
- **1.1/E-4:** strict flow indentation, which matches YAML 1.2.2 (yaml-test-suite
  9C9N).

Profiles pinned to 1.0 must keep their expectations unchanged.

## Decision

1. **Revision 1 stays as it is.** `yamlprims-core` r1 and its merge variants keep
   citing `spec-v1.0` and are not edited. A specification change is always a
   new profile revision.
2. **Revision 2 profiles** cite `spec-v1.1` by tag, commit, and the sha256 of
   the specification bytes:
   - `yamlprims-core`, `yamlprims-core-merge-apply`, and
     `yamlprims-core-merge-as-key` model single-document entrypoints;
   - `yamlprims-core-stream` models multi-document entrypoints.

   E-2 is the case where the two give different answers for the same input.
3. **Profiles may state `flow_indentation`** (`lenient` or `strict`). Every r2
   profile states `strict`. When the field is absent, the setting is whatever
   the cited specification says. For r1, that is spec 1.0's lenient setting.
4. **Span convention `scalar-alias` r2** takes E-1's end rule for block
   scalars and keeps revision 1's start rule (the block indicator or opening
   quote). That start differs from yamlprims' content start, and the convention
   text says so. A convention that matches yamlprims exactly would be a
   separately named convention, once quoted-scalar starts are pinned down.
   Empty-node spans stay undefined.
5. **Format-level truth comes from YAML, not from any one parser.** Two new
   cases disagree with some widely used parsers, and both follow YAML 1.2.2
   and yaml-test-suite:
   - a bare `...` is a valid stream with zero documents (HWV9);
   - under-indented flow entries are invalid (9C9N).
6. **Generated material under r2.** The small recipes (numeric truth and all
   goldens) get copies bound to the r2 profiles in the smoke tier. Their
   expectations are identical to the r1 recipes, because none of their inputs
   is affected by E-1 to E-4; this was checked input by input. The large
   boolean and collision tables stay bound to r1 for now. Duplicating them
   would use about 96% of the conformance tier's output cap. They move to r2
   when r1 is retired.

## Consequences

- A consumer qualifying against specification 1.1 has r2-bound expectations
  for the numeric truth and golden recipes and the cases listed above. The
  boolean and collision truth tables remain r1-bound, and r1-bound rows are
  never counted as r2 results. Empty-node, collection, and explicit-root
  locations and parent containment are not yet asserted, so this is not
  complete coverage of 1.1/E-1 or 1.1/E-2. `docs/coverage.md` records these
  gaps.
- The copied recipes keep their recorded value and typed expectations
  unchanged. They record no spans, so the E-1 span change does not apply to
  them.
- Old pins keep reproducing their original expectations byte for byte.
- When a parser disagrees with YAML on HWV9 or 9C9N, it shows up as a mismatch
  on a format-level case and is not hidden inside a profile.
