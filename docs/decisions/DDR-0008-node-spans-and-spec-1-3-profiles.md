---
Record: DDR-0008
Title: Node spans and profile revisions for yamlprims specification 1.3
Status: Proposed
Date: 2026-10-15
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0008: Node spans and profile revisions for yamlprims specification 1.3

## Context

The yamlprims specification is at revision 1.3 (`spec-v1.3`). Revisions 1.2
and 1.3 pin exact source anchors for zero-width nodes:
- empty block scalars;
- omitted scalars in nested block collections;
- tag wrappers and their inner scalars;
- zero-width collections, which never move.

They also pin keep-chomping values at end of input, the binary64-to-binary32
conversion path, and a UTF-8-only input surface.

These anchors are spans of **value nodes**, not of events. An event index
cannot tell a tag wrapper from its inner node, and it cannot name a node of a
document root that has no scalar event. The specification also requires that
the new anchors are not bound to a profile claiming unchanged 1.2 behavior, and
that historical profiles keep their bindings.

## Decision

1. **Profiles citing 1.3 are new revisions.** These revisions cite `spec-v1.3`
   by tag, commit, and the sha256 of the specification bytes:
   - `yamlprims-core`, `yamlprims-core-merge-apply`,
     `yamlprims-core-merge-as-key`, and `yamlprims-core-stream` r3;
   - `yamlprims-core-limits` r2.

   Every earlier profile is unchanged and keeps its own citation. There is no
   profile citing 1.2; anchors pinned by 1.2 are recorded under the 1.3
   profiles, where the specification restates them unchanged.
2. **Node spans are a separate expectation layer, `node_locations`.** A node
   location names a node convention, a profile and its revision, and a list of
   spans. Each span selects a node by:
   - a document index;
   - a path of steps into that profile's value expectation: `key` and
     `value` (by entry index), `item` (by sequence index), and `inner` (a tagged
     node's inner node).

   A path ending at a tagged node selects the wrapper. The validator requires
   that the path resolves in that profile's expected value tree, that the node's
   kind is one the convention defines, and that the span lies within the input.
3. **Span conventions are either event-keyed or node-keyed.** An event-keyed
   convention lists `defined_events`. A node-keyed convention states
   `selects: value-node` and lists `defined_nodes`. A convention is never both.
   Event-keyed `locations` are unchanged.
4. **Node convention `yamlprims-node` r1** defines only what revision 1.3
   pins:
   - omitted scalars;
   - block scalars with no source content line, including the two whose span
     at end of input is not zero-width (`k: |\n\n` and `k: |\n`, both
     `[3, 4)`);
   - tag wrappers that share such a scalar's span;
   - zero-width collections.

   "Empty" here means empty in the source, not in the decoded value: a
   keep-chomping block scalar with no content line can decode to line feeds,
   and a zero-width mapping can hold an entry. Spans of other nodes remain
   undefined.
5. **Generated material under 1.3.** These recipes get copies bound to the new
   profiles:
   - numeric truth;
   - all goldens;
   - float thresholds, escapes, merge pairs, and tag trees;
   - the tag-wrapper limit boundaries.

   Each copy's records are identical to its source apart from the profile
   revision, identity, and review text, which was checked record by record.
   No input in these sets is affected by 1.2 or 1.3:
   - they record no spans;
   - every input is valid UTF-8;
   - none ends in an unterminated spaces-only line under keep chomping;
   - their f32 expectations already round the binary64 value.

   The large boolean and collision tables stay bound to their original
   profiles, as under DDR-0006.

## Consequences

- A consumer qualifying against specification 1.3 has 1.3-bound expectations
  for the anchor rows, the end-of-input keep-chomping values, the f32 conversion
  example, the UTF-8 input surface, and every copied recipe.
- Spans of nodes with source content, collection extents, and error envelopes
  are not yet asserted.
- Old pins reproduce their original expectations byte for byte.
- A later convention revision can define more node kinds without changing the
  meaning of existing node spans.
