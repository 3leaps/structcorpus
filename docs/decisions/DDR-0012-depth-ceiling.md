---
Record: DDR-0012
Title: Depth ceiling at configured maximum 255
Status: Accepted
Date: 2026-10-23
Owner: devlead
---

# DDR-0012: Depth ceiling at configured maximum 255

## Context

DDR-0011 pins the section 6 boundary rows at `max_depth` 128. The same
section says to test levels 254, 255, and 256 at the legal configured
ceiling, 255. A profile has one limit set, so those rows need their own
profile. They do not replace the 128 rows.

## Decision

1. **Historical profiles and recipes stay byte-for-byte.** `depth-boundaries`
   r1 remains bound to `yamlprims-core-depth128` r1. Its digest does not
   change. Profiles that cite revision 1.3 are unchanged.
2. **`yamlprims-core-depth255` r1** cites the same `spec-v1.4` bytes as the
   revision 4 policy profiles. `max_depth` is 255. Every other limit is
   above the six rows, including the tree those rows would build and the
   64-byte registration of `&a []`.
3. **`depth-ceiling` r1 is provisional.** `generators/yaml/spec14_boundaries.py`
   emits it. Each input is ASCII with one final LF.
   - `depth-254` and `depth-255` load. `depth-256` is
     `limit_exceeded` / `max_depth` / configured 255, at the 256th `[`.
   - `alias-252` and `alias-253` load. `alias-254` is the same limit error.
     Its source collection maximum is 255, so the failure is alias placement
     at 256.
4. **Error records stay as they are.** This record does not add a source
   byte, line, or column. The case id and the input bytes identify the row.
5. **Rows still not covered.** The section 6 merge-height examples,
   registration below/at/above, pairwise and all-four copy ties,
   completed-key weight, and the section 7.1 paired failures.
   1.4/E-4 is an encoder metric and is not corpus material.

## Consequences

- A consumer qualifying the configured depth ceiling uses `depth-ceiling` r1.
  The 128 rows remain the qualification for `max_depth` 128.
- The generator refuses this set unless `max_depth` is 255, and it refuses
  an alias row whose source level exceeds `max_depth` before placement.
- `docs/coverage.md` lists this slice as provisional. The rows in item 5
  stay planned.
