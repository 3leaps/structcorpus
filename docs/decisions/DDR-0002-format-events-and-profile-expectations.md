---
Record: DDR-0002
Title: Format-level events separate from profile-bound expectations
Status: Proposed
Date: 2026-10-13
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0002: Format-level events separate from profile-bound expectations

## Context

A YAML value tree is not neutral. It already encodes scalar-resolution
choices (Core schema or otherwise), how non-core tags are represented, where
spans begin, how merge keys apply, and how resources are counted. If cases
record only a value tree, every case quietly inherits one adapter's policy, and
another conforming engine can "fail" expectations that YAML itself never set.

Budget and accounting expectations make this clear. "A tagged scalar counts
as two nodes" or "a merged-in entry is charged as a copy" are rules of one
adapter's contract. No other engine can be wrong against them.

## Decision

1. **Three independent kinds of expectation; a case carries any non-empty subset:**
   - **`events`** are format-level and engine-neutral. They record validity
     under a named format revision (for example YAML 1.2.2), plus the event
     *content*: kinds, order, anchors, tags, scalar styles, and values. The
     notation is the yaml-test-suite event format, pinned to a named
     upstream revision. The event content carries no positions. Any engine
     can be checked against it, and upstream yaml-test-suite cases map onto
     it.
   - **`value`** is profile-bound. It records the resolved value tree, typed
     conversions, and errors under a named, versioned profile. A profile
     cites the published normative specification revision and accepted
     errata that define it, by public reference only (SecDR-0001). The
     `value` representation is the profile's own wire schema, and nothing
     claims it is universal.
   - **`locations`** are optional and separate from both. YAML does not
     define which offsets a parser should report for an event, so offsets
     are always stated under a named, versioned **span convention** that
     the corpus defines and pins. A case can therefore be fully conformant on
     syntax and events while its location conformance is reported
     separately, or is not applicable.
2. **Budgets, accounting, and limit errors are profile-only.** Families such
   as tag accounting, alias expansion, merge budget, and depth state their
   format-level part as `events` (valid or invalid, plus the stream).
   Everything numeric about cost goes under a profile.
3. **Locations are byte offsets only.** Location expectations record byte
   offsets into the original input, under a named span convention that
   defines start and end points for each node kind, aliases (both
   definition and use), and empty nodes.
   Line, column (1-based, in Unicode scalar values), and UTF-16 offsets are
   derived by corpus tooling and never typed by hand. Which bytes count as
   line breaks is part of the profile; YAML 1.2 treats U+2028, U+2029, and
   NEL as content. Unknown or inapplicable positions are explicit, never zero.
4. **Errors use a closed phase vocabulary:** `input` (encoding, input size),
   `syntax`, `resolution` (tag/value mismatch, numeric range), `structure`
   (duplicate key, merge, anchors), `limit` (with a required limit name), and
   `typed`. Adding a phase is a schema change. Exact prose is normative only
   in cases that test diagnostic formatting. Which error wins when several
   apply is profile policy, so a "first error" expectation must name a
   profile.
5. **When engines agree, it is recorded as an observation.** Observed
   behavior goes into run results, never into expectations. Cases whose
   oracle is unresolved are marked `provisional` and do not count toward a
   qualification pass.
6. **Metadata is versioned JSON.** Unknown `schema_version` values fail
   validation, and duplicate keys in JSON metadata are errors. Schemas and at
   least one complete example of each record kind land before any bulk import
   of cases.

## Consequences

- Upstream suites and non-reference engines can use the format-level event layer
  without adopting any adapter's policy.
- A consumer that disagrees with a profile adds a profile. Format truth is not
  in dispute.
- Tooling has to derive line and column from offsets. That code is small and
  removes a whole class of hand-typed drift.
- Profiles are versioned separately from the schema. Being schema-compatible
  does not mean two releases have the same expectations.
