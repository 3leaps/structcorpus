---
Record: DDR-0011
Title: Profile revisions and boundary recipes for yamlprims specification 1.4
Status: Accepted
Date: 2026-10-23
Owner: devlead
---

# DDR-0011: Profile revisions and boundary recipes for yamlprims specification 1.4

## Context

The yamlprims specification revision 1.4 (`spec-v1.4`) defines loader rules
that revision 1.3 left open:

- **1.4/E-1.** Source collection level `p` starts at 0. A collection at that
  position consumes level `p + 1`. Scalars and retained tags add no level.
  Each document resets `p`. Completed height `H` is 0 for a scalar, `H(inner)`
  for a tagged node, and `1 + max(H(children))` for a sequence or mapping
  (`max` of an empty collection is 0). An alias copy at position `p` requires
  `p + H(anchor) <= max_depth`.
- **1.4/E-2.** Registering an anchored subtree charges its logical weight to
  `max_owned_bytes` and charges no extra nodes.
- **1.4/E-3.** Source validation precedes construction. An ordinary mapping
  admits an entry only after the key and value are built; capacity is checked
  before duplicate identity. Copy-limit ties resolve as depth, then nodes,
  then expanded nodes, then owned bytes. `max_key_bytes` is the completed
  key's logical weight.
- **1.4/E-4.** Names the encoder's error-key nesting separately from loader
  height. Encoder output stays outside this corpus.

Section 6 gives the depth rows this record pins. At `max_depth` 128, `S_127(0)`
and `S_128(0)` load, and `S_129(0)` fails at the 129th `[`. `S_n(Y)` is `n`
opening `[` bytes, the fragment `Y`, and `n` closing `]` bytes. For
`{a: &a [], b: S_k(*a)}`, `k` of 125 and 126 load, and `k` of 127 fails at the
alias: the source collection maximum is 128 and the insertion check is 129.
Section 5.2's admission order, restated in section 7.1, gives the entry rows.
With a cap of 2, `{a: 0, b: 0}` loads, `{a: 0, a: 1}` is `duplicate_key`, and
both `{a: 0, b: 0, a: 1}` and `{a: 0, b: 0, c: 1}` are
`LimitExceeded(max_mapping_entries)`.

DDR-0009 recorded depth ladders as events only because revision 1.3 did not
define the count. Those ladders stay events only. New expectations get new
profiles.

## Decision

1. **Earlier profiles stay byte-for-byte.** Every profile that cites
   `spec-v1.3` or an earlier tag keeps its citation, limits, and recipes.
   A specification change is a new profile revision. The event-only depth
   ladder is one of those recipes.
2. **Revision 4 policy profiles cite `spec-v1.4`** by tag, commit, and the
   sha256 of `docs/spec/yamlprims-spec.md`:
   - `yamlprims-core` r4, `yamlprims-core-merge-apply` r4, and
     `yamlprims-core-merge-as-key` r4 model single-document entrypoints;
   - `yamlprims-core-stream` r4 models multi-document entrypoints.

   Their policy fields match the revision 3 profile of the same id. They carry
   no cases in this record. A later recipe that wants default options cites
   r4. It does not retarget an r3 recipe.
3. **Explicit limits are separate profile ids.** A profile has one limit set,
   and a `configured` value has to equal that set (DDR-0009).
   - `yamlprims-core-depth128` r1 sets `max_depth` to 128. Every other limit
     is above the six depth rows, including the tree those rows would build.
   - `yamlprims-core-entries2` r1 sets `max_mapping_entries` to 2. Every other
     limit is above the four entry rows, counting key and value nodes built
     before admission.

   Both cite the same `spec-v1.4` bytes as the r4 policy profiles. Neither is
   a revision of `yamlprims-core-limits` or `yamlprims-core-stress`.
4. **Two smoke recipes, both provisional.**
   `generators/yaml/spec14_boundaries.py` emits them. Each input is ASCII
   with one final LF, which is the line ending in the section 6 recipes.
   - `depth-boundaries` r1 is bound to `yamlprims-core-depth128` r1.
     `depth-127` and `depth-128` load. `depth-129` is
     `limit_exceeded` / `max_depth` / configured 128.
     `alias-125` and `alias-126` load. `alias-127` is the same limit error.
     Its source collection maximum is 128, so the failure is alias placement.
   - `entry-admission` r1 is bound to `yamlprims-core-entries2` r1.
     `entries-two` loads. `entries-duplicate` is `duplicate_key`.
     `entries-third-duplicate` and `entries-third-new` are
     `limit_exceeded` / `max_mapping_entries` / configured 2.
     The third-duplicate row repeats `a` and still selects the entry cap,
     which is the capacity-before-identity order.
     `entries-nan-at-cap` is `{a: 0, b: 0, .nan: 1}` and is `invalid_key`.
     The mapping is already at the entry cap. Key validity is checked first.
     `entries-nan-before-value` is `{.nan: !!int nope}` and is `invalid_key`.
     Its value is not resolved. The case id and the input identify which
     check fired.

   The generator refuses a row whose other load budgets are already over, and
   it refuses an alias row whose source level exceeds `max_depth` before
   placement. Registration of `&a []` adds 64 owned bytes and no node.
5. **Error records stay as they are.** A limit error may name `phase`,
   `kind`, `limit`, and `configured`. This record does not add a source
   byte, line, or column. The case id and the input bytes identify the row.
   Paired-failure offsets in section 7.1 wait until a site field exists.
6. **Rows not in this record.** Depth 254/255/256 at limit 255, the section 6
   merge-height examples, registration below/at/above, pairwise and all-four
   copy ties, completed-key weight, and the section 7.1 paired failures.
   1.4/E-4 is an encoder metric and is not corpus material.

## Consequences

- A consumer qualifying revision 1.4 depth and ordinary-entry admission uses
  `depth-boundaries` r1 and `entry-admission` r1. r3 results are not r4
  results. The new policy profiles are the citation for later default-option
  rows; they are not coverage by themselves.
- Historical pins keep their bytes. Hydrating an older recipe still yields
  that recipe's recorded digest.
- The generator's arithmetic is the expectation. It does not call a parser
  and it does not import another project's outputs.
- `docs/coverage.md` lists this slice as provisional and lists the remaining
  revision 1.4 rows as planned.
- Cases and recipes stay `provisional` until a reviewer distinct from the
  author marks them reviewed.
