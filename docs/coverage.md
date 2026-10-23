# Coverage

Release stages are defined in
[PDR-0001](decisions/PDR-0001-staged-releases.md).

| Area | Status |
| --- | --- |
| Repository rules validator (names, sizes, byte-exact attributes, strict JSON) | Implemented |
| Case, profile, span-convention, and upstream-lock schemas (DDR-0003) | Implemented |
| Canonical JSON (JCS subset) serializer | Implemented |
| Example cases: one per expectation layer, all `provisional` | Implemented (8) |
| Scalar resolution, duplicate-key, and numeric truth generator (59,484 generated cases, `yamlprims-core` r1, provisional) | Implemented |
| Typed-conversion expectations (DDR-0005): integer widths, `f32`, `f64`, `bool`, `string`, `option-bool` | Implemented (numbers and booleans r2) |
| Hand-checked boundary goldens, including merge `apply` and `as-key` profiles (125 cases) | Implemented, provisional |
| yamlprims specification 1.1 profiles (`yamlprims-core` r2, stream, merge variants) and span convention `scalar-alias` r2 (DDR-0006) | Implemented |
| Specification 1.1 cases: document cardinality, strict flow indentation, block-scalar span ends (12 cases) | Implemented, provisional |
| Numeric truth and goldens bound to r2 profiles (smoke tier) | Implemented |
| Boolean and collision truth tables bound to r2 profiles | Planned: when the r1 profiles retire (conformance tier budget) |
| yamlprims specification 1.3 profiles (`yamlprims-core` r3 and variants, `yamlprims-core-limits` r2), node-span convention `yamlprims-node` r1 with `node_locations` (DDR-0008) | Implemented |
| Specification 1.2 and 1.3 anchor rows (19 cases, 21 node spans), end-of-input keep chomping, f32 conversion path, UTF-8 input surface; generated recipes copied to the 1.3 profiles | Implemented, provisional |
| Spans of non-empty nodes and collection extents | Planned |
| Wire-format goldens for a specific implementation's encoder | Not planned: an implementation's encoded output is its own conformance surface, not engine-neutral corpus material |
| Non-hazardous adversarial recipes: exact binary64/binary32 rounding thresholds, double-quoted escapes, inline versus aliased merge pairs, tag-heavy trees and tag-wrapper limit boundaries (312 generated cases, provisional) | Implemented |
| Committed adversarial cases: alias validity, block-scalar chomping and indentation with LF and CRLF, location precision (BOM, multibyte, tab, lone CR, U+2028), diagnostics inputs, the UTF-8 input gate (NUL, invalid UTF-8, UTF-16, UTF-32), and explicit and composite keys (58 cases, provisional) | Implemented |
| Limit boundaries for alias events, expanded nodes, mapping entries, and nodes under `yamlprims-core-limits` r2, with configured values (DDR-0009) | Implemented, provisional |
| Stress ladders: alias fan-out, nested fan-out, many keys, late failure, depth (stress tier, hazardous, budgeted); expected errors bound to `yamlprims-core-stress` r1. The depth ladder stays event-only | Implemented, provisional |
| yamlprims specification 1.4 policy profiles (`yamlprims-core` r4 and stream, merge-apply, and merge-as-key variants) citing `spec-v1.4`. No cases are bound to those four profiles in this slice (DDR-0011) | Implemented |
| Depth boundaries at `max_depth` 128 (`S_127`/`S_128`/`S_129` and alias `k` 125/126/127) under `yamlprims-core-depth128` r1, and ordinary-entry admission at `max_mapping_entries` 2 under `yamlprims-core-entries2` r1, including `{a: 0, b: 0, .nan: 1}` and `{.nan: !!int nope}` (DDR-0011) | Implemented, provisional |
| Depth ceiling at `max_depth` 255 (`S_254`/`S_255`/`S_256` and alias `k` 252/253/254) under `yamlprims-core-depth255` r1 (DDR-0012) | Implemented, provisional |
| Remaining specification 1.4 rows: merge height, registration totals, copy-limit ties, completed-key weight, and paired failures that need a source site | Planned |
| Bounded hydrate / verify for generated recipes (DDR-0004) | Implemented |
| Containment runner with self-tests (SecDR-0002): bounded execution of a caller-supplied command | Implemented |
| Running hostile YAML cases through a parser command (`runner.py run`), one container per case with its budgets | Implemented; comparing output with expectations is the consumer driver's job |
| `list`, stress-tier plumbing, recipe hazards and budgets, explicit-limits profile `yamlprims-core-limits` (DDR-0007) | Implemented |
| Event notation `structcorpus-events/1` (DDR-0010): schema, validator, reference codec with pinned-runner vectors | Implemented; no case uses it yet, and consumers report it as unsupported until they read it |
| yaml-test-suite import, Windows/Linux parity matrix | Planned, 0.3 |
| Binding lifetime and streaming input surfaces | Unsupported until a consumer exposes them |
| JSON, XML | Reserved |
